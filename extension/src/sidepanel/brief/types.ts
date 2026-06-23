/** BriefData — mirrors backend SGR contract (specs/FEAT-012-sgr-contract.md). */

export interface BriefContact {
  role: string;
  company: string;
  companyDetail: string;
  budgetNote: string;
}

export interface BriefProfileTag {
  label: string;
  color: "blue" | "green" | "amber";
}

export interface BriefFocusPoint {
  headline: string;
  detail: string;
}

export interface BriefRoi {
  value: string;
  description: string;
}

export interface BriefComparisonSide {
  name: string;
  price: string;
  pros: string;
  cons: string;
}

export interface BriefComparison {
  current: BriefComparisonSide;
  proposed: BriefComparisonSide;
}

export interface BriefObjection {
  question: string;
  answer: string;
}

export interface BriefData {
  contact: BriefContact;
  profileTags: BriefProfileTag[];
  painPoints: string[];
  focusPoints: BriefFocusPoint[];
  roi?: BriefRoi | null;
  comparison?: BriefComparison | null;
  objections: BriefObjection[];
  fullBrief: string;
}
