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