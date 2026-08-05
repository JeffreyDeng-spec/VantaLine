import { useMemo } from "react";
import { Search } from "lucide-react";
import { searchCandidates, type SearchCandidate } from "../utils/search";

interface LibrarySearchBoxProps {
  value: string;
  onChange: (value: string) => void;
  candidates: SearchCandidate[];
  placeholder: string;
}

export function LibrarySearchBox({ value, onChange, candidates, placeholder }: LibrarySearchBoxProps) {
  const suggestions = useMemo(() => searchCandidates(candidates, value), [candidates, value]);

  return (
    <div className="library-search-box">
      <label className="search-field">
        <span>搜索</span>
        <span className="search-input-wrap">
          <Search size={16} aria-hidden="true" />
          <input placeholder={placeholder} value={value} onChange={(event) => onChange(event.currentTarget.value)} />
        </span>
      </label>
      {suggestions.length ? (
        <div className="search-suggestions">
          {suggestions.map((candidate) => (
            <button type="button" className="search-suggestion" key={candidate.id} onClick={() => onChange(candidate.label)}>
              {candidate.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
