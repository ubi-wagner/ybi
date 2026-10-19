/* What a 990 function is called, written down once.
 *
 * `worklistKinds.js` is this file's reason for existing: there were three
 * hand-kept maps of what a worklist kind means, each missing different
 * kinds, and the failure mode was never a broken screen — it was a screen
 * that starts speaking SQL. `MANAGEMENT_AND_GENERAL` on a transaction a
 * controller is about to put in front of a sponsor is exactly that, and
 * `Form990.jsx` held a private map of three where the enum has four.
 *
 * The four are `decision.function_990`'s own values, read from the schema.
 * `NOT_APPLICABLE` is the compensation block — cost lifted out of the three
 * columns the return prints rather than spread across them — so it is named
 * for what it is and never shown as blank.
 */
export const FUNCTION_990 = {
  PROGRAM: "Program services",
  MANAGEMENT_AND_GENERAL: "Management and general",
  FUNDRAISING: "Fundraising",
  NOT_APPLICABLE: "Not applicable",
};

/* The short form, for a column beside figures. A table that has to fit six
   columns cannot carry "Management and general" either, and clipping the
   federal treatment to make room for it is the worse trade: whether a cost
   is ALLOWABLE is the thing a sponsor asks about. */
export const FUNCTION_990_SHORT = {
  PROGRAM: "Program",
  MANAGEMENT_AND_GENERAL: "Mgmt & general",
  FUNDRAISING: "Fundraising",
  NOT_APPLICABLE: "Not applicable",
};

/* A value the map does not hold is shown as itself rather than as a blank:
   a function nobody has named is a thing to go and look at, and an empty
   cell reads as one nobody recorded. */
export const fn990 = (v, short = false) =>
  (short ? FUNCTION_990_SHORT : FUNCTION_990)[v] || v || "";
