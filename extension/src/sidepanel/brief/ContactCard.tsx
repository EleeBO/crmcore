import type { BriefContact, BriefProfileTag } from "./types";

function makeInitials(role: string): string {
  const words = role.trim().split(/\s+/);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  if (words.length === 1 && words[0]) return words[0].slice(0, 2).toUpperCase();
  return "";
}

interface Props {
  contact: BriefContact;
  tags: BriefProfileTag[];
}

export function ContactCard({ contact, tags }: Props) {
  if (!contact.role) return null;

  const initials = makeInitials(contact.role);
  const company = [contact.company, contact.companyDetail]
    .filter(Boolean)
    .join(" \u00B7 ");

  return (
    <div class="brief-contact-card">
      <div class="brief-contact-row">
        {initials && <div class="brief-avatar">{initials}</div>}
        <div class="brief-contact-info">
          <div class="brief-contact-role">{contact.role}</div>
          {company && <div class="brief-contact-company">{company}</div>}
          {contact.budgetNote && (
            <div class="brief-contact-budget">{contact.budgetNote}</div>
          )}
        </div>
      </div>
      {tags.length > 0 && (
        <div class="brief-tags">
          {tags.slice(0, 3).map((tag) => (
            <span
              key={tag.label}
              class={`brief-tag brief-tag--${tag.color}`}
            >
              {tag.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
