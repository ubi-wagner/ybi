-- 115 · Contractor or subrecipient, decided once and written down.
--
-- 2 CFR 200.1 takes **the first $25,000 of each subaward** into MTDC and no
-- more. A contract for services goes in whole. So the same payment sits in the
-- base or mostly outside it depending on a determination under 200.331 — and
-- nothing in this system had ever recorded one.
--
-- `scripts/burdened_buildup.py` shipped with a `SUBAWARD_CAP` that never fired,
-- because the invoices categorise every one of these as `CONSULTANT`. The cap
-- logic existed and no line ever reached it: a control that cannot fire for the
-- case it exists to catch, which is the shape this repository has paid for more
-- than any other.
--
-- Four payees on the 2025 federal awards clear the cap by $234,575.89 between
-- them, which is $40,112 to $57,987 of indirect resting on a judgment nobody
-- has made:
--
--     LTM         Defense & Energy Systems LLC     102,000.00
--     DRIVE-AM    Elevate Systems                  101,075.89
--     DIG-ENG     (no payee on the ledger line)    100,000.00
--     LTM         (no payee on the ledger line)     31,500.00
--
-- **UNDETERMINED is the default and is never a pass.** 200.331 says the
-- substance of the relationship governs and not the form, so neither the
-- invoice category nor the account name settles it. Until somebody answers,
-- the register says so and the rate carries the exposure on its face — the
-- intake rule applied to a classification: *a blank is unanswered, and
-- unanswered is a value.*
--
-- The five tests are 200.331(a) for a subrecipient and 200.331(b) for a
-- contractor. They are recorded as written text rather than as booleans: the
-- determination is the judgment, and which tests carried it is the reason a
-- reviewer will ask for.
CREATE TABLE IF NOT EXISTS party_determination (
    determination_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    period            text NOT NULL REFERENCES fiscal_period(period),
    objective_id      text NOT NULL REFERENCES cost_objective(objective_id),
    payee             text NOT NULL,
    amount            numeric(14,2) NOT NULL,
    determination     text NOT NULL DEFAULT 'UNDETERMINED'
                          CHECK (determination IN
                                 ('CONTRACTOR', 'SUBRECIPIENT', 'UNDETERMINED')),
    -- Why. A determination with no reasoning is the next person's puzzle, and
    -- 200.331 turns on substance, so the substance has to be on the row.
    basis             text NOT NULL DEFAULT '',
    agreement_ref     text NOT NULL DEFAULT '',
    decided_by        text NOT NULL DEFAULT '',
    decided_at        timestamptz,
    CONSTRAINT one_determination_per_party
        UNIQUE (period, objective_id, payee),
    -- A determination that is made carries who made it and why; one that is
    -- not carries neither. Half a determination is the shape that reads as an
    -- answer and is not one.
    CONSTRAINT a_determination_says_who_and_why CHECK (
        (determination = 'UNDETERMINED'
         AND decided_by = '' AND decided_at IS NULL)
        OR (determination <> 'UNDETERMINED'
            AND length(btrim(decided_by)) > 0
            AND decided_at IS NOT NULL
            AND length(btrim(basis)) >= 40))
);

COMMENT ON TABLE party_determination IS
  'Contractor or subrecipient under 2 CFR 200.331, per payee per objective. '
  'Decides whether MTDC takes the payment whole or only its first $25,000.';

-- What each determination does to the base, and what is still open.
CREATE OR REPLACE VIEW v_subaward_exposure AS
SELECT p.period,
       p.objective_id,
       p.payee,
       p.amount,
       p.determination,
       p.basis,
       p.decided_by,
       -- 200.1: a subaward reaches MTDC only to its first $25,000.
       CASE p.determination
           WHEN 'SUBRECIPIENT' THEN least(p.amount, 25000::numeric)
           WHEN 'CONTRACTOR'   THEN p.amount
           ELSE NULL                     -- unanswered is not a number
       END AS in_mtdc,
       greatest(p.amount - 25000::numeric, 0)::numeric(14,2) AS at_stake,
       CASE p.determination
           WHEN 'UNDETERMINED' THEN 'NO DATA'
           ELSE 'TIES'
       END AS state,
       CASE p.determination
           WHEN 'UNDETERMINED' THEN
               'nobody has determined whether this party is a contractor or a '
               'subrecipient, so whether MTDC takes ' ||
               to_char(p.amount, 'FM999,999,990.00') || ' or 25,000.00 is open'
           ELSE ''
       END AS needs
  FROM party_determination p;

COMMENT ON VIEW v_subaward_exposure IS
  'How much of each party''s payment reaches MTDC, and how much turns on a '
  '200.331 determination nobody has made. UNDETERMINED is NO DATA, not a pass.';
