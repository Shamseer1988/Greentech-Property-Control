"use client";

import { useState } from "react";
import {
  useReactTable, getCoreRowModel, getSortedRowModel, getPaginationRowModel,
  flexRender, type ColumnDef, type SortingState, type PaginationState,
  type Updater,
} from "@tanstack/react-table";
import { ArrowUp, ArrowDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { selectClass } from "./dialog";

const DEFAULT_PAGE_SIZES = [10, 25, 50, 100];

export function DataTable<T>({
  columns,
  data,
  loading = false,
  emptyMessage = "No rows",
  pageSizeOptions = DEFAULT_PAGE_SIZES,
  defaultPageSize = 25,
  maxBodyHeight,
  onRowClick,
  getRowId,
  footer,
  manualPagination = false,
  pageCount: manualPageCount,
  totalCount,
  pagination: controlledPagination,
  onPaginationChange,
}: {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  loading?: boolean;
  emptyMessage?: string;
  pageSizeOptions?: number[];
  defaultPageSize?: number;
  /** Caps table body height and adds vertical scroll — use for tall lists. */
  maxBodyHeight?: string;
  onRowClick?: (row: T) => void;
  getRowId?: (row: T, index: number) => string;
  /** A `<tr>` (or several) rendered in a `<tfoot>` below the page's rows —
   *  build it from the full, unpaginated `data` so totals stay correct
   *  regardless of which page is showing. Not meaningful in
   *  `manualPagination` mode, since `data` is only the current page. */
  footer?: React.ReactNode;
  /** Server-side pagination mode — `data` holds only the current page's
   *  rows. Requires `pageCount`, `pagination` and `onPaginationChange`.
   *  Client-side mode (the default) is unaffected when this is omitted. */
  manualPagination?: boolean;
  pageCount?: number;
  /** True row count across all pages, for the "N rows" label — falls back
   *  to `data.length` (this page's size) when omitted. */
  totalCount?: number;
  pagination?: PaginationState;
  onPaginationChange?: (updater: Updater<PaginationState>) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [localPagination, setLocalPagination] = useState({ pageIndex: 0, pageSize: defaultPageSize });
  const pagination = manualPagination ? controlledPagination! : localPagination;
  const setPagination = manualPagination ? onPaginationChange! : setLocalPagination;

  const table = useReactTable({
    data,
    columns,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    ...(manualPagination
      ? { manualPagination: true, pageCount: manualPageCount ?? -1 }
      : { getPaginationRowModel: getPaginationRowModel() }),
    getRowId,
  });

  const rows = table.getRowModel().rows;
  const pageCount = table.getPageCount();
  const pageIndex = table.getState().pagination.pageIndex;
  const rowCountLabel = manualPagination ? (totalCount ?? data.length) : data.length;

  return (
    <div className="glass rounded-xl overflow-hidden">
      <div className="overflow-x-auto" style={maxBodyHeight ? { maxHeight: maxBodyHeight, overflowY: "auto" } : undefined}>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border sticky top-0 bg-card/80 backdrop-blur z-10">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => {
                  const sortable = header.column.getCanSort();
                  const sort = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      onClick={sortable ? header.column.getToggleSortingHandler() : undefined}
                      className={"py-2 px-3 whitespace-nowrap " + (sortable ? "select-none cursor-pointer hover:text-foreground" : "")}
                    >
                      {header.isPlaceholder ? null : (
                        <span className="inline-flex items-center gap-1">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sort === "asc" && <ArrowUp className="h-3 w-3" />}
                          {sort === "desc" && <ArrowDown className="h-3 w-3" />}
                        </span>
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length} className="py-10 text-center text-muted-foreground">Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={columns.length} className="py-10 text-center text-muted-foreground">{emptyMessage}</td></tr>
            ) : rows.map((row) => (
              <tr
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                className={"border-b border-border/60 hover:bg-accent/30 " + (onRowClick ? "cursor-pointer" : "")}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="py-2 px-3 whitespace-nowrap">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {footer && !loading && rows.length > 0 && (
            <tfoot className="border-t-2 border-border font-semibold bg-card/40">
              {footer}
            </tfoot>
          )}
        </table>
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap px-3 py-2 border-t border-border text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <span>{rowCountLabel} row{rowCountLabel === 1 ? "" : "s"}</span>
          {pageCount > 0 && <span>· Page {pageIndex + 1} of {pageCount}</span>}
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5">
            Rows per page
            <select
              className={selectClass + " h-7 w-auto text-xs py-0"}
              value={table.getState().pagination.pageSize}
              onChange={(e) => table.setPageSize(Number(e.target.value))}
            >
              {pageSizeOptions.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <div className="flex items-center gap-0.5">
            <button type="button" onClick={() => table.setPageIndex(0)} disabled={!table.getCanPreviousPage()}
              className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
              <ChevronsLeft className="h-3.5 w-3.5" />
            </button>
            <button type="button" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}
              className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <button type="button" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}
              className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
            <button type="button" onClick={() => table.setPageIndex(pageCount - 1)} disabled={!table.getCanNextPage()}
              className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
              <ChevronsRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
