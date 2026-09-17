-- 114 · Every invoice's lines add to its header, or the register says so.
--
-- `load_invoices_2025.py` wrote AAMEN invoice 9079 with a stated payment of
-- 26,087.57 and **no `invoice_line` rows at all**. Its line prints on the face
-- without the quantity and rate columns the other eleven carry, so a regex
-- requiring `1 <rate> <amount>` matched nothing, and the loader's own footing
-- check opened `if inv["lines"] and ...` — which excludes precisely the case
-- it exists to catch. A payment with nothing under it is not a tidier invoice;
-- it is an unreadable one.
--
-- Nothing downstream could see it. `v_invoice_income_tie` compares the
-- register to `3900 Grant Income` on the **header** totals, and those are
-- right — 313,050.84 to the cent. The gap is entirely between an invoice and
-- its own lines, and no control had ever looked there.
--
-- What it cost: `POST /api/restate` rebuilds the as-billed reading from the
-- lines, so it measured eleven invoices while reporting twelve and understated
-- AAMEN's billing by 26,087.57 — which understates the position by the same
-- amount, in the direction that has YBI keep money it cannot support.
--
-- This is the QuickBooks rule the imports already hold — *every printed
-- subtotal must equal what sits under it* — asked of the invoice register,
-- which is the one register that never had it.
--
-- Three states, not two. An invoice nobody has entered lines for is `NO DATA`
-- and is never a pass: an empty set matching an empty set perfectly is 029's
-- lesson, and this defect is exactly that shape one register along.
CREATE OR REPLACE VIEW v_invoice_footing_check AS
WITH lined AS (
    SELECT i.invoice_id, i.period, i.objective_id, i.invoice_number,
           i.invoice_date, i.total AS header_total,
           count(l.*)                        AS lines,
           COALESCE(sum(l.amount), 0)::numeric(14,2) AS line_total
      FROM invoice i
      LEFT JOIN invoice_line l ON l.invoice_id = i.invoice_id
     WHERE i.status <> 'WITHDRAWN'
     GROUP BY i.invoice_id, i.period, i.objective_id, i.invoice_number,
              i.invoice_date, i.total
)
SELECT period, objective_id, invoice_number, invoice_date,
       header_total, lines, line_total,
       COALESCE(header_total, 0) - line_total AS variance,
       CASE
           WHEN lines = 0 THEN 'NO DATA'
           WHEN COALESCE(header_total, 0) = line_total THEN 'TIES'
           ELSE 'OPEN'
       END AS state,
       CASE
           WHEN lines = 0 THEN
               'the invoice states a total and carries no line — nothing on '
               'its face has been read'
           WHEN COALESCE(header_total, 0) <> line_total THEN
               'the lines do not add to the total printed on the invoice'
           ELSE ''
       END AS needs
  FROM lined;

COMMENT ON VIEW v_invoice_footing_check IS
  'Every invoice''s lines against the total on its own face. NO DATA is an '
  'invoice nobody has read the lines off, and is never a pass.';
