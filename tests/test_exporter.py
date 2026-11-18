"""Tests des noms de fichiers et de l'export local."""

from lofima.exporter import LocalFolderExporter, safe_filename


def test_safe_filename_windows_rules():
    assert safe_filename('AC/DC - Back In Black?') == "AC_DC - Back In Black_.mp3"
    assert safe_filename("CON") == "_CON.mp3"
    assert safe_filename("  ...  ") == "Sans titre.mp3"
    assert safe_filename("Title.") == "Title.mp3"


def test_export_renames_and_avoids_collisions(tmp_path):
    source = tmp_path / "src.mp3"
    source.write_bytes(b"data")
    exporter = LocalFolderExporter(tmp_path / "out")

    first = exporter.export(source, "A.mp3")
    # Une autre musique avec le même nom ne doit pas écraser la première
    second = exporter.export(source, "A.mp3")
    assert (first, second) == ("A.mp3", "A (2).mp3")

    # Réexport de la même musique sous son propre nom : pas de doublon
    assert exporter.export(source, "A.mp3", previous_name="A.mp3") == "A.mp3"

    # Renommage : l'ancien fichier disparaît
    renamed = exporter.export(source, "B.mp3", previous_name="A (2).mp3")
    assert renamed == "B.mp3"
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["A.mp3", "B.mp3"]
