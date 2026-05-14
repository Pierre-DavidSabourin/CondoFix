====================================================================
FDP Import – Archiving Parameters Explained

The FDP import script supports flexible archiving behavior before
inserting new rows.

The parameters below control how existing records are archived
(historique = 1) before import.

--archive-existing

Enables the UPDATE that sets historique = 1 on existing rows for the
selected IDClient, subject to the filters below.

If this flag is not provided, no existing records are archived.

--archive-part-syndicat {all|0|1}

Adds a filter on PartSyndicat when archiving.

all -> No filter (default). Applies to all rows.
0 -> Archive only rows where PartSyndicat = 0
1 -> Archive only rows where PartSyndicat = 1

This allows selective archiving depending on whether the intervention
is assumed by the syndicate or not.

--archive-except-idgroupe <ID>

Adds a category-based exclusion rule.

Archives everything EXCEPT rows whose IDCategorie belongs to:

categories.IDClient = <client_id>
AND categories.IDGroupe = <ID>

Example:

--archive-except-idgroupe 9

Means:

Keep active all rows belonging to IDGroupe = 9
(e.g., "Z – Parties communes à usage restreint").
Archive all others (subject to other filters).

Filter Logic

When multiple parameters are used, filters are combined using AND logic.

A row will be archived only if it matches ALL applicable filters.

Common Use Cases

Archive everything except Group 9

--archive-existing
--archive-except-idgroupe 9

Effect:
Archives all existing rows for the client,
but keeps IDGroupe = 9 active.

Archive only non-syndicate rows, but keep Group 9 active

--archive-existing
--archive-part-syndicat 0
--archive-except-idgroupe 9

Effect:
Archives rows where PartSyndicat = 0,
except those belonging to IDGroupe = 9.
Rows where PartSyndicat = 1 remain unchanged.

Legacy behavior (before group filter existed)

Archive only syndicate rows:

--archive-existing
--archive-part-syndicat 1

Archive everything:

--archive-existing
Important

If --archive-existing is not specified, no archiving occurs.

Always run with --dry-run first in PROD to validate row counts.

Filters are cumulative; review combinations carefully before commit.

====================================================================
====================================================================
LOCAL DRY-RUN — Memphré 2112 (IDClient = 4) — Keep IDGroupe 9 active

Set environment variables (local)

$env:CF_DB_HOST = 'localhost'
$env:CF_DB_USER = 'CONDO_FIX_DEV'
$env:CF_DB_PASSWORD = '4Evcondo1723#$#'
$env:CF_DB_NAME = 'condofix$condofix'

Run dry-run import (archive existing EXCEPT IDGroupe=9)

cd C:\WORKSPACE\Clone\CondoFix\mysite_PA_july11

python .\condofix\scripts\Import_FDP.py `
  --client-id 3 `
  --xlsx .\condofix\20260301_Import_fds_prevoyance_2112.xlsx `
  --archive-existing `
  --archive-except-idgroupe 9 `
  --dry-run

NOTES:

For Donald’s requirement (“conserver Z / groupe 9; mettre le reste historique”),
do NOT use --archive-part-syndicat 1. Keep default behavior (all).

If you add --archive-part-syndicat 1, you would only archive PartSyndicat=1 rows,
which is not what Donald requested.

====================================================================
SQL CHECKS — BEFORE DRY-RUN / BEFORE REAL RUN (IDClient = 4)

-- A) Totals + active vs historical
SELECT COUNT(*) AS total
FROM fondsprevoyance
WHERE IDClient = 4;

SELECT COUNT(*) AS historique_1
FROM fondsprevoyance
WHERE IDClient = 4 AND historique = 1;

SELECT COUNT(*) AS actif_0_or_null
FROM fondsprevoyance
WHERE IDClient = 4 AND (historique = 0 OR historique IS NULL);

-- B) Active rows that belong to IDGroupe=9 (Z group)
SELECT COUNT(*) AS actif_groupe_9
FROM fondsprevoyance fp
WHERE fp.IDClient = 4
AND (fp.historique = 0 OR fp.historique IS NULL)
AND fp.IDCategorie IN (
SELECT c.IDCategorie
FROM categories c
WHERE c.IDClient = 4 AND c.IDGroupe = 9
);

-- C) Active rows that are NOT in IDGroupe=9 (these are the ones that SHOULD become historique=1 after archiving)
SELECT COUNT(*) AS actif_not_groupe_9
FROM fondsprevoyance fp
WHERE fp.IDClient = 4
AND (fp.historique = 0 OR fp.historique IS NULL)
AND fp.IDCategorie NOT IN (
SELECT c.IDCategorie
FROM categories c
WHERE c.IDClient = 4 AND c.IDGroupe = 9
);

-- D) Optional: distribution by PartSyndicat (for analysis only)
SELECT PartSyndicat, COUNT(*) AS actif_count
FROM fondsprevoyance
WHERE IDClient = 4
AND (historique = 0 OR historique IS NULL)
GROUP BY PartSyndicat;

====================================================================
EXPECTED RESULTS AFTER ARCHIVING (REAL RUN)

After the archiving step (real run, not dry-run), you should observe:

actif_groupe_9 stays the same (still active)

actif_not_groupe_9 becomes 0 (all archived)

historique_1 increases by (previous actif_not_groupe_9 count)

total stays the same (unless you insert new rows)

Then insertion adds new rows (typically active by default).

====================================================================
REAL RUN (when ready — remove --dry-run)

python .\condofix\scripts\Import_FDP.py --client-id 4
--xlsx .\condofix\20260301_Import_fds_prevoyance_2112.xlsx --archive-existing
--archive-except-idgroupe 9

====================================================================


--**************************             old *********************
Run the Import_FDP.py locally like this

$env:CF_DB_HOST = 'localhost'
$env:CF_DB_USER = 'CONDO_FIX_DEV'
$env:CF_DB_PASSWORD = '4Evcondo1723#$#'
$env:CF_DB_NAME = 'condofix$condofix'


python .\condofix\scripts\Import_FDP.py `
  --client-id 3 `
  --xlsx .\condofix\20260103_Urbano_Importation_FDP.xlsx `
  --archive-existing `
  --archive-part-syndicat 1 `
  --archive-except-idgroupe 9 `
  --dry-run
 ******************************************************************************
test sql before

SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1; -- 124
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1 AND historique = 1; -- 0
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1 AND (historique = 0 OR historique IS NULL); -- 124

SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 3;
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 3 AND (historique = 0 OR historique IS NULL);
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 3 AND (historique = 0 OR historique IS NULL) AND PartSyndicat = 1;
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 3 AND (historique = 0 OR historique IS NULL) AND PartSyndicat = 0;

 ******************************************************************************
 To do the real run
 ******************************************************************************
python .\condofix\scripts\Import_FDP.py `
  --client-id 1 `
  --xlsx .\condofix\20260103_Urbano_Importation_FDP.xlsx `
  --archive-existing `
  --archive-part-syndicat 1 `

 ******************************************************************************
 After
 ******************************************************************************
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1; -- 216
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1 AND historique = 1; -- 124
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1 AND (historique = 0 OR historique IS NULL); -- 92

SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 3 AND historique = 1 AND PartSyndicat = 1;
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 3 AND (historique = 0 OR historique IS NULL) AND PartSyndicat = 0;


******************************************************************************
In PA use this
******************************************************************************


cd /home/CondoFix/mysite

export CF_DB_HOST='CondoFix.mysql.pythonanywhere-services.com'
export CF_DB_USER='CondoFix'
export CF_DB_PASSWORD='LacNations_1999'
export CF_DB_NAME='CondoFix$condofix'


python condofix/scripts/Import_FDP.py \
  --client-id 3 \
  --xlsx condofix/20260103_Urbano_Importation_FDP.xlsx \
  --archive-existing \
  --archive-part-syndicat 1 \
  --dry-run