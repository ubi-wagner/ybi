-- Seed: period, an open decision set, the baseline lane, cost objectives, and
-- the one award whose terms we have in hand.

INSERT INTO fiscal_period (period, start_date, end_date)
VALUES ('2025','2025-01-01','2025-12-31'), ('2024','2024-01-01','2024-12-31')
ON CONFLICT (period) DO NOTHING;

INSERT INTO import_profile (profile_id, report, column_aliases, options, created_by, notes)
VALUES
 ('qbo-gl-v1','GENERAL_LEDGER',
  '{"date":["date","txn date","transaction date"],
    "txn_type":["transaction type","type"],
    "num":["num","no.","number","doc num"],
    "name":["name","vendor","customer","name/vendor/employee","payee","customer/project"],
    "memo":["memo/description","description","memo"],
    "split":["split","account"],
    "amount":["amount"],"debit":["debit"],"credit":["credit"],
    "balance":["balance","running balance"],
    "class_":["class"],"location":["location"]}'::jsonb,
  '{"account_in_section_header": true, "strip_totals": true}'::jsonb,
  'seed','QBO General Ledger report export, CSV path'),
 ('qbo-time-v1','TIME_ACTIVITY',
  '{"date":["date","activity date"],
    "employee":["employee","name","vendor/employee"],
    "customer":["customer","customer/project","customer:job"],
    "service":["service","service item"],
    "hours":["duration","hours","time"],
    "billable":["billable","billable?"],
    "memo":["description","memo","notes"],"class_":["class"]}'::jsonb,
  '{}'::jsonb,'seed','Time Activities by Employee Detail')
ON CONFLICT (profile_id) DO NOTHING;

INSERT INTO decision_set (period, label)
SELECT '2025','2025 build'
 WHERE NOT EXISTS (SELECT 1 FROM decision_set WHERE period='2025');

INSERT INTO lane (period, name, kind, set_id, purpose, created_by)
SELECT '2025','2025-baseline','BASELINE', ds.set_id,
       'The classifications and assumptions that will be submitted','seed'
  FROM decision_set ds
 WHERE ds.period='2025'
   AND NOT EXISTS (SELECT 1 FROM lane WHERE period='2025' AND kind='BASELINE')
 LIMIT 1;

INSERT INTO cost_objective (objective_id, period, label, objective_type, is_federal) VALUES
 ('DRIVE-AM','2025','Drive AM','FEDERAL AWARD',true),
 ('HYBRID-II','2025','Hybrid II','FEDERAL AWARD',true),
 ('LTM','2025','Last Tactical Mile','FEDERAL AWARD',true),
 ('DIG-ENG','2025','Digital Engineering','FEDERAL AWARD',true),
 ('AAMEN','2025','AAMEN','FEDERAL AWARD',true),
 ('DLA','2025','DLA','FEDERAL AWARD',true),
 ('IIOT','2025','IIOT','FEDERAL AWARD',true),
 ('RISING-TIDES','2025','Rising Tides','PROGRAM',false),
 ('ESP','2025','ODSA / ESP','STATE/LOCAL PROGRAM',false),
 ('MBAC','2025','MBAC','PROGRAM',false),
 ('HUB','2025','Hub','PROGRAM',false),
 ('YOUTH','2025','Youth Entrepreneurship','PROGRAM',false),
 ('XJET','2025','Xjet / Manufacturing Services','MANUFACTURING/SERVICE',false),
 ('VGV','2025','VGV Investment Fund','PROGRAM',false),
 ('AM-OTHER','2025','America Makes — other','PROGRAM',false),
 ('RENTAL','2025','Rental / Landlord','RENTAL',false),
 ('YBI-GA','2025','YBI General Administration','ADMINISTRATION',false),
 ('FUNDRAISING','2025','Fundraising / B&P','FUNDRAISING/B&P',false)
ON CONFLICT (objective_id) DO NOTHING;

-- Terms transcribed from the executed sub-recipient agreement, 8 Sep 2023.
-- Rising Tides is seeded non-federal pending the ARC award document; the
-- controller's own workbook classes it federal. That conflict is deliberate
-- and visible rather than silently resolved.
INSERT INTO award (award_id, objective_id, sponsor, prime_agreement, instrument,
                   ceiling_federal, cost_share_required, period_start, period_end,
                   rate_method, citation)
VALUES ('AM-HYBRID-P2','HYBRID-II','NCDMM / America Makes','AFRL FA8650-20-2-5700',
        'Cost reimbursement, no fee', 500043, 104000, '2023-09-08','2025-10-10',
        'DE_MINIMIS_10','Sub-Recipient Agreement executed 8 September 2023')
ON CONFLICT (award_id) DO NOTHING;

INSERT INTO award_budget_line (award_id, line, federal_amount, cost_share) VALUES
 ('AM-HYBRID-P2','LABOR',449043,0),
 ('AM-HYBRID-P2','TRAVEL',4500,0),
 ('AM-HYBRID-P2','CONSULTANT',40000,0),
 ('AM-HYBRID-P2','ODC',6500,104000)
ON CONFLICT (award_id, line) DO NOTHING;

INSERT INTO pool_definition (pool, period, base_type, description) VALUES
 ('DIRECT','2025','MTDC','Cost assigned to a final cost objective'),
 ('FRINGE','2025','SALARIES_WAGES','Employee benefits, applied on a wage base'),
 ('OVERHEAD','2025','MTDC','Facilities and related occupancy'),
 ('G&A','2025','MTDC','General and administrative'),
 ('RENTAL_DIRECT','2025','MTDC','Tenant space — not allocable to federal awards'),
 ('FUNDRAISING','2025','MTDC','Fundraising and bid & proposal'),
 ('UNALLOWABLE','2025','MTDC','Expressly unallowable under 200.420-475'),
 ('EXCLUDED','2025','MTDC','Outside the cost model')
ON CONFLICT (pool) DO NOTHING;
