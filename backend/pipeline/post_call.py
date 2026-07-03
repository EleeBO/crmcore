"""Post-call processing: merge diarized channels, compute analytics, store in Redis."""

from __future__ import annotations

import asyncio
import json
from statistics import mean
from typing import Any

from backend.logger import logger
from backend.pipeline.audio_buffer import AudioBuffer

# Re-export DTOs for backward compatibility — importers can still use
# `from backend.pipeline.post_call import CallAnalytics, DiarizedUtterance`
from backend.pipeline.types import (  # noqa: F401
    CallAnalytics,
    DiarizedUtterance,
    call_analytics_to_wire_json,
)
from backend.pipeline.yandex_async import (
    AsyncRecognitionResult,
    YandexAsyncRecognizer,
)
from backend.storage.keys import EVAL_TTL, eval_analytics, eval_transcript

_INTERRUPTION_THRESHOLD_MS = 300
_MAX_PAUSE_FOR_RESPONSE_MS = 10_000


class PostCallProcessor:
    """Orchestrate post-call diarization and analytics computation."""

    MIN_DURATION_S = 5.0

    def __init__(
        self,
        recognizer: YandexAsyncRecognizer,
        redis: Any,
        session_id: str,
    ) -> None:
        self._recognizer = recognizer
        self._redis = redis
        self._session_id = session_id

    async def process(self, audio_buffer: AudioBuffer) -> CallAnalytics | None:
        """Run post-call diarization pipeline. Returns None on skip/failure."""
        try:
            return await self._process_inner(audio_buffer)
        except Exception as exc:
            logger.exception(f"Post-call processing failed: {exc!r}")
            return None
        finally:
            audio_buffer.clear()

    async def _process_inner(self, audio_buffer: AudioBuffer) -> CallAnalytics | None:
        # Guards
        rep_dur = audio_buffer.duration_s("rep")
        client_dur = audio_buffer.duration_s("client")
        if max(rep_dur, client_dur) < self.MIN_DURATION_S:
            logger.info("Post-call skip: call too short")
            return None
        if audio_buffer.exceeds_limit():
            logger.warning("Post-call skip: buffer exceeds gRPC limit")
            return None

        # Build WAV per channel
        rep_wav = audio_buffer.get_wav("rep")
        client_wav = audio_buffer.get_wav("client")

        # Parallel recognition
        try:
            rep_result, client_result = await asyncio.gather(
                self._recognizer.recognize(rep_wav),
                self._recognizer.recognize(client_wav),
            )
        except Exception as exc:
            logger.error(f"Yandex async recognition failed: {exc!r}")
            return None

        # Both channels must succeed
        if not rep_result.utterances and not client_result.utterances:
            logger.warning("Post-call: both channels returned 0 utterances")
            return None
        if not rep_result.utterances or not client_result.utterances:
            logger.warning("Post-call: one channel returned 0 utterances, skipping")
            return None

        # Merge with offset compensation
        offset_ms = audio_buffer.start_offset_ms()
        merged = self._merge(rep_result, client_result, offset_ms)

        # Compute analytics
        analytics = self._compute_analytics(merged)

        # Store in Redis (atomic pipeline)
        await self._store_results(analytics)

        return analytics

    def _merge(
        self,
        rep: AsyncRecognitionResult,
        client: AsyncRecognitionResult,
        offset_ms: int,
    ) -> list[DiarizedUtterance]:
        """Merge two channel results into time-sorted timeline."""
        utterances: list[DiarizedUtterance] = []
        for u in rep.utterances:
            utterances.append(
                DiarizedUtterance(
                    speaker="rep", text=u.text, start_ms=u.start_ms, end_ms=u.end_ms
                )
            )
        for u in client.utterances:
            utterances.append(
                DiarizedUtterance(
                    speaker="client",
                    text=u.text,
                    start_ms=u.start_ms + offset_ms,
                    end_ms=u.end_ms + offset_ms,
                )
            )
        utterances.sort(key=lambda u: u.start_ms)
        return utterances

    def _compute_analytics(
        self,
        utterances: list[DiarizedUtterance],
    ) -> CallAnalytics:
        """Compute all metrics from utterance timings."""
        rep_time_ms = sum(
            u.end_ms - u.start_ms for u in utterances if u.speaker == "rep"
        )
        client_time_ms = sum(
            u.end_ms - u.start_ms for u in utterances if u.speaker == "client"
        )
        total_ms = rep_time_ms + client_time_ms

        rep_words = sum(len(u.text.split()) for u in utterances if u.speaker == "rep")
        client_words = sum(
            len(u.text.split()) for u in utterances if u.speaker == "client"
        )

        rep_time_min = rep_time_ms / 60_000 if rep_time_ms > 0 else 1
        client_time_min = client_time_ms / 60_000 if client_time_ms > 0 else 1

        by_rep, by_client = self._count_interruptions(utterances)
        avg_pause = self._avg_pause_before_response(utterances)

        return CallAnalytics(
            total_duration_s=total_ms / 1000,
            rep_talk_time_s=rep_time_ms / 1000,
            client_talk_time_s=client_time_ms / 1000,
            rep_talk_ratio=rep_time_ms / total_ms if total_ms > 0 else 0.0,
            rep_speech_rate_wpm=rep_words / rep_time_min,
            client_speech_rate_wpm=client_words / client_time_min,
            rep_word_count=rep_words,
            client_word_count=client_words,
            interruptions_by_rep=by_rep,
            interruptions_by_client=by_client,
            avg_rep_pause_before_response_s=avg_pause,
            utterances=utterances,
        )

    def _count_interruptions(
        self,
        utterances: list[DiarizedUtterance],
    ) -> tuple[int, int]:
        """Count overlapping utterances between speakers. Overlap > 300ms.

        Utterances are sorted by start_ms, so b always starts at or after a.
        Therefore b is always the interrupter when overlap is detected.
        """
        by_rep = 0
        by_client = 0
        for i, a in enumerate(utterances):
            for b in utterances[i + 1 :]:
                if a.speaker == b.speaker:
                    continue
                overlap = min(a.end_ms, b.end_ms) - max(a.start_ms, b.start_ms)
                if overlap > _INTERRUPTION_THRESHOLD_MS:
                    # b started later (list sorted by start_ms) → b is interrupter
                    if b.speaker == "rep":
                        by_rep += 1
                    else:
                        by_client += 1
        return by_rep, by_client

    def _avg_pause_before_response(
        self,
        utterances: list[DiarizedUtterance],
    ) -> float:
        """Average gap between client utterance end and next rep start."""
        pauses: list[float] = []
        for i, u in enumerate(utterances):
            if u.speaker != "client":
                continue
            # Find next rep utterance
            for j in range(i + 1, len(utterances)):
                if utterances[j].speaker == "rep":
                    gap_ms = utterances[j].start_ms - u.end_ms
                    if 0 < gap_ms < _MAX_PAUSE_FOR_RESPONSE_MS:
                        pauses.append(gap_ms / 1000)
                    break
        return mean(pauses) if pauses else 0.0

    async def _store_results(self, analytics: CallAnalytics) -> None:
        """Atomic Redis pipeline: replace transcript + store analytics."""
        eval_key = eval_transcript(self._session_id)
        analytics_key = eval_analytics(self._session_id)

        diarized = [
            json.dumps(
                {
                    "speaker": u.speaker,
                    "text": u.text,
                    "start_ms": u.start_ms,
                    "end_ms": u.end_ms,
                }
            )
            for u in analytics.utterances
        ]

        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.delete(eval_key)
            if diarized:
                pipe.rpush(eval_key, *diarized)
            pipe.expire(eval_key, EVAL_TTL)
            pipe.set(
                analytics_key,
                call_analytics_to_wire_json(analytics),
                ex=EVAL_TTL,
            )
            await pipe.execute()
            logger.info(
                f"Post-call results stored: {len(diarized)} utterances, "
                f"analytics for session {self._session_id}"
            )
        except Exception as exc:
            logger.error(f"Redis store failed: {exc!r}")
