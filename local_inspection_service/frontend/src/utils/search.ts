export interface SearchCandidate {
  id: string;
  label: string;
  keywords?: string[];
}

export function normalizeSearchText(value: unknown) {
  return String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function fuzzyScore(text: string, query: string) {
  if (!query) return 0;
  const directIndex = text.indexOf(query);
  if (directIndex >= 0) return directIndex;
  let score = 0;
  let cursor = 0;
  for (const char of query) {
    const index = text.indexOf(char, cursor);
    if (index < 0) return Number.POSITIVE_INFINITY;
    score += index - cursor + 1;
    cursor = index + 1;
  }
  return score + text.length;
}

export function searchCandidateText(candidate: SearchCandidate) {
  return normalizeSearchText([candidate.label, candidate.id, ...(candidate.keywords || [])].join(" "));
}

export function candidateMatches(candidate: SearchCandidate, query: string) {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return true;
  return Number.isFinite(fuzzyScore(searchCandidateText(candidate), normalizedQuery));
}

export function searchCandidates(candidates: SearchCandidate[], query: string, limit = 6) {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return [];
  return candidates
    .map((candidate) => ({ candidate, score: fuzzyScore(searchCandidateText(candidate), normalizedQuery) }))
    .filter((item) => Number.isFinite(item.score))
    .sort((a, b) => a.score - b.score || a.candidate.label.localeCompare(b.candidate.label, "zh-Hans-CN"))
    .slice(0, limit)
    .map((item) => item.candidate);
}
