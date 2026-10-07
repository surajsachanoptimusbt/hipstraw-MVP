# Contract: markdown demo report

The `report` step writes `reports/<runId>.md`. A HipStraw team member can read it without operating
the system (FR-017). It is generated only from stored records and makes no model calls. It has no
person fields or person entities, and contains no email addresses or phone numbers (FR-018). Person
names may appear only incidentally, inside quoted excerpts.

## Sections, in order

1. **Title**: `Invoice Alpha: first position report (<runId>)`
2. **Run summary**:
   - the program and its source URL;
   - the experiment context and candidate ID;
   - the run date and model;
   - the counts: returned, included, excluded, needs verification, and shortfall with its reason.
3. **First position**: segment, company archetype, buyer, problem, trigger, and primary interests.
4. **Constraints in force**: the size thresholds and the three metros (CSA names), taken from
   `runs.constraintsInForce`.
5. **Hypothesis check (SC-003)**: the number of included companies against the minimum of 3, and a
   blank spot-check table for the reviewer: company, meets constraints (yes/no), genuine interest
   signal (yes/no), and notes.
6. **Included companies**: one subsection per company:
   - name, website, and confidence band;
   - fit claims (buyer, problem, trigger), each with its primary interests;
   - interest signals, each labeled pain or exploration;
   - headquarters, size signals, and the falsifier;
   - the Review reason;
   - a citations table: claim, URL, date (or "unknown"), reliability, excerpt in quotes.
7. **Needs verification**: one row per company, with what is missing (its unknowns and the failed
   rules) and the Review reason.
8. **Excluded**: one row per company, with the failed rule and the Review reason.
9. **Unknowns and conflicts**: every unknown and every preserved conflict (for example, two employee
   counts with their citations).
10. **Traceability**: one line per included company, linking first position → origin source →
    evidence IDs → review decision ID.
11. **Footer**: the baseline snapshot ID, the report SHA-256, and the statement "All companies above
    were found in sources retrieved during this run; every citation marked passing was checked for
    an exact excerpt match."

A company never appears in more than one of sections 6, 7, and 8.
