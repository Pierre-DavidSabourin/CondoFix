Run the Import_FDP.py locally like this

$env:CF_DB_HOST = 'localhost'
$env:CF_DB_USER = 'CONDO_FIX_DEV'
$env:CF_DB_PASSWORD = '4Evcondo1723#$#'
$env:CF_DB_NAME = 'condofix$condofix'


python .\condofix\scripts\Import_FDP.py `
  --client-id 1 `
  --xlsx .\condofix\20260103_Urbano_Importation_FDP.xlsx `
  --archive-existing `
  --dry-run
 ******************************************************************************
test sql before

SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1; -- 124
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1 AND historique = 1; -- 0
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1 AND (historique = 0 OR historique IS NULL); -- 124
 ******************************************************************************
 To do the real run
 ******************************************************************************
python .\condofix\scripts\Import_FDP.py `
  --client-id 1 `
  --xlsx .\condofix\20260103_Urbano_Importation_FDP.xlsx `
  --archive-existing `


 ******************************************************************************
 After
 ******************************************************************************
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1; -- 216
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1 AND historique = 1; -- 124
SELECT COUNT(*) FROM fondsprevoyance WHERE IDClient = 1 AND (historique = 0 OR historique IS NULL); -- 92

******************************************************************************
In PA use this
******************************************************************************


cd /home/CondoFix/mysite

export CF_DB_HOST='CondoFix.mysql.pythonanywhere-services.com'
export CF_DB_USER='CondoFix'
export CF_DB_PASSWORD='LacNations_1999'
export CF_DB_NAME='CondoFix$condofix'


python condofix/scripts/Import_FDP.py \
  --client-id 1 \
  --xlsx condofix/20260103_Urbano_Importation_FDP.xlsx \
  --archive-existing \
  --dry-run