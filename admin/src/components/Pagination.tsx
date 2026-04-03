interface PaginationProps {
  page: number;
  pages: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, pages, onPageChange }: PaginationProps) {
  if (pages <= 1) return null;

  const range: number[] = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(pages, page + 2);
  for (let i = start; i <= end; i++) range.push(i);

  return (
    <div className="pagination">
      <button disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Prev</button>
      {range.map((p) => (
        <button key={p} className={p === page ? "active" : ""} onClick={() => onPageChange(p)}>
          {p}
        </button>
      ))}
      <span>/ {pages}</span>
      <button disabled={page >= pages} onClick={() => onPageChange(page + 1)}>Next</button>
    </div>
  );
}
