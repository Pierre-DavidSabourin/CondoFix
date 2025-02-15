import shutil
import os

# copie et collage avec le nouveau nom de fichier

source_path="../documentation/Demo_docs/Cascades_Case_Study-FR.pdf"
ch_dir="C:/Users\DOnal\Documents\Projets Programmation\mysite_PA_july11\documentation\Test_docs"
dest_path=os.path.join(ch_dir, "new_file.pdf")
shutil.move(source_path, dest_path)