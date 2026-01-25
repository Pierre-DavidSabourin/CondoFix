CondoFix — Import Entretien Préventif (preventif)
================================================

Script:
  condofix/scripts/Import_EntretiensPreventif.py

Purpose:
  Import an “entretien préventif” spreadsheet (XLSX) into the MySQL table `preventif`.

Key behavior:
  - Reads XLSX directly (openpyxl) — no CSV encoding issues.
  - Robust header normalization (case/accents/spaces/dots).
  - Explicit month mapping for duplicate labels (M/J/A repeats).
  - Hours columns:
      * If only “Employé h.” is provided -> 1 insert (IDIntervenant = Concierge)
      * If only “Fournisseur h.” is provided -> 1 insert (IDIntervenant = Autre)
      * If both are provided -> 2 inserts (one for each intervenant)
      * If neither is provided -> insert with IDIntervenant=0 and HresEstimees=0 (same as Donald’s script)
  - Transactional:
      * --dry-run  => ROLLBACK at end
      * no dry-run => COMMIT at end

Header expectations (XLSX first row):
  Élément | Description | Catégorie | Fréquence ans | J | F | M | A | M_1 | J_2 | J_3 | A_4 | S | O | N | D | Date prochain | Employé h. | Fournisseur h.

Notes:
  - IDCategorie must be INT (e.g., 20, 21, 22, etc.).
  - FreqAns must be INT (number of years).
  - Month columns should be 0/1.
  - Date prochain must parse to YYYY-MM-DD (Excel date is fine).

------------------------------------------------
LOCAL — environment variables (PowerShell)
------------------------------------------------

$env:CF_DB_HOST = 'localhost'
$env:CF_DB_USER = 'CONDO_FIX_DEV'
$env:CF_DB_PASSWORD = '4Evcondo1723#$#'
$env:CF_DB_NAME = 'condofix$condofix'

Identify intervenant IDs for the client (LOCAL example: IDClient=1):
  SELECT IDIntervenant, IDClient, NomIntervenant
  FROM condofix$condofix.intervenants
  WHERE IDClient = 1 AND NomIntervenant LIKE '%Concierge%';
  -- result: 1 (Concierge)

  SELECT IDIntervenant, IDClient, NomIntervenant
  FROM condofix$condofix.intervenants
  WHERE IDClient = 1 AND NomIntervenant LIKE '%Autre%';
  -- result: 59 (Autre)

Dry-run (LOCAL):
python .\condofix\scripts\Import_EntretiensPreventif.py `
  --client-id 1 `
  --xlsx .\condofix\ImportEntretien2112.xlsx `
  --id-concierge 1 `
  --id-interv-autre 59 `
  --dry-run

Real run (LOCAL):
python .\condofix\scripts\Import_EntretiensPreventif.py `
  --client-id 1 `
  --xlsx .\condofix\ImportEntretien2112.xlsx `
  --id-concierge 1 `
  --id-interv-autre 59

Basic checks (LOCAL):
  SELECT COUNT(*) FROM condofix$condofix.preventif WHERE IDClient = 1;
  SELECT COUNT(*) FROM condofix$condofix.preventif WHERE IDClient = 1 AND IDIntervenant = 1;
  SELECT COUNT(*) FROM condofix$condofix.preventif WHERE IDClient = 1 AND IDIntervenant = 59;

------------------------------------------------
PROD (PythonAnywhere) — environment variables
------------------------------------------------

cd /home/CondoFix/mysite

export CF_DB_HOST='CondoFix.mysql.pythonanywhere-services.com'
export CF_DB_USER='CondoFix'
export CF_DB_PASSWORD='LacNations_1999'
export CF_DB_NAME='CondoFix$condofix'

Identify intervenant IDs for the target client (PROD example: IDClient=4):
  SELECT IDIntervenant, IDClient, NomIntervenant
  FROM CondoFix$condofix.intervenants
  WHERE IDClient = 4 AND NomIntervenant LIKE '%Concierge%';
  -- result: 78 (Concierge)

  SELECT IDIntervenant, IDClient, NomIntervenant
  FROM CondoFix$condofix.intervenants
  WHERE IDClient = 4 AND NomIntervenant LIKE '%Autre%';
  -- result: 71 (Autre)

Dry-run (PROD):
python condofix/scripts/Import_EntretiensPreventif.py \
  --client-id 4 \
  --xlsx condofix/ImportEntretien2112.xlsx \
  --id-concierge 78 \
  --id-interv-autre 71 \
  --dry-run

Real run (PROD):
python condofix/scripts/Import_EntretiensPreventif.py \
  --client-id 4 \
  --xlsx condofix/ImportEntretien2112.xlsx \
  --id-concierge 78 \
  --id-interv-autre 71

Basic checks (PROD):
  SELECT COUNT(*) FROM CondoFix$condofix.preventif WHERE IDClient = 4;
  SELECT COUNT(*) FROM CondoFix$condofix.preventif WHERE IDClient = 4 AND IDIntervenant = 78;
  SELECT COUNT(*) FROM CondoFix$condofix.preventif WHERE IDClient = 4 AND IDIntervenant = 71;

Reminder:
  Column name `Dec` is a reserved keyword in some contexts; SQL uses `\`Dec\`` when needed.
  Our INSERT already wraps it as `\`Dec\``.
