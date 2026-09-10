-- =====================================================================
-- Notes on classification groups
--
-- The controller works in account/payee groups, and most reasoning is about
-- the group rather than about one of its lines: "confirm with the CEO whether
-- any of the government relations retainer is non-lobbying advocacy" belongs
-- to the retainer, not to each of its twelve payments.
--
-- Evidence stays line-level deliberately. The evidence-grade gate reads
-- attachments on lines, and a document tied to specific dollars survives a
-- group being split later. A note does not carry that weight.
-- =====================================================================

ALTER TYPE attach_target ADD VALUE IF NOT EXISTS 'LEDGER_GROUP';
