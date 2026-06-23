import type { BriefData } from "./types";
import { ComparisonCards } from "./ComparisonCards";
import { ContactCard } from "./ContactCard";
import { Divider } from "./Divider";
import { ExpandButton } from "./ExpandButton";
import { FocusPoints } from "./FocusPoints";
import { ObjectionCards } from "./ObjectionCards";
import { PainPoints } from "./PainPoints";
import { RoiHighlight } from "./RoiHighlight";

interface Props {
  data: BriefData;
  compact?: boolean;
}

export function BriefPanel({ data, compact }: Props) {
  if (compact) {
    return (
      <div class="brief-panel">
        <ContactCard contact={data.contact} tags={data.profileTags} />
        <FocusPoints points={data.focusPoints} />
      </div>
    );
  }

  return (
    <div class="brief-panel">
      <ContactCard contact={data.contact} tags={data.profileTags} />
      <Divider />
      <FocusPoints points={data.focusPoints} />
      <PainPoints points={data.painPoints} />
      <Divider />
      <RoiHighlight roi={data.roi} />
      <ComparisonCards comparison={data.comparison} />
      <Divider />
      <ObjectionCards objections={data.objections} />
      <ExpandButton text={data.fullBrief} />
    </div>
  );
}
