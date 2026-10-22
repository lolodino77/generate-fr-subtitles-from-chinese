"""Tests unitaires : outils texte, construction des lignes et des blocs."""
from video_ocr.models import TextBox, TextLine
from video_ocr.ocr.lines import boxes_to_lines, expand_with_neighbours, group_blocks
from video_ocr.ocr.text_utils import (
    cjk_ratio, comparison_key, count_cjk, detect_script, normalize_text, similarity, to_simplified,
)

# Caractères traditionnels dont la forme simplifiée diffère
TRAD = "這個問題很難解決，我們應該怎麼辦？"
SIMP = "这个问题很难解决，我们应该怎么办？"


def test_traditional_vs_simplified_detection() -> None:
    assert detect_script(TRAD) == "traditional"
    assert detect_script(SIMP) == "simplified"
    assert detect_script("hello") == "none"
    assert to_simplified(TRAD) == SIMP


def test_original_text_preserved_by_normalization() -> None:
    # La normalisation ne convertit pas l'écriture : seule la clé de comparaison passe en simplifié
    assert "這" in normalize_text(TRAD)
    assert comparison_key(TRAD) == comparison_key(SIMP)


def test_similarity_ignores_punctuation_and_script() -> None:
    assert similarity(TRAD, SIMP.replace("？", "")) == 1.0
    assert similarity("謝謝你們的幫助", "錢不是萬能的") < 0.3
    assert similarity("", "") == 1.0


def test_cjk_ratio() -> None:
    assert count_cjk("對！abc") == 1
    assert cjk_ratio("對對ab") == 0.5
    assert cjk_ratio("ปัญหานี้แก้ยาก") == 0.0


def test_boxes_to_lines_merges_rows_and_classifies() -> None:
    boxes = [
        TextBox("但沒有錢", 0.99, (100, 200, 300, 240)),
        TextBox("是萬萬不能的", 0.98, (310, 202, 600, 242)),
        TextBox("錢不是萬能的", 0.97, (200, 140, 500, 180)),
        TextBox("ปัญหา", 0.6, (220, 260, 480, 290)),
        TextBox("雜訊", 0.3, (0, 0, 10, 10)),  # score trop faible pour du chinois
    ]
    lines = boxes_to_lines(boxes, min_score=0.5, min_cjk_ratio=0.5)
    by_text = {ln.text: ln for ln in lines}
    assert [ln.text for ln in lines] == ["雜訊", "錢不是萬能的", "但沒有錢是萬萬不能的", "ปัญหา"]  # tri vertical
    assert by_text["錢不是萬能的"].is_chinese and by_text["但沒有錢是萬萬不能的"].is_chinese
    assert not by_text["ปัญหา"].is_chinese
    assert not by_text["雜訊"].is_chinese  # score trop faible


def test_stacked_lines_with_overlapping_boxes_not_merged() -> None:
    # Cas réel (Reel DeyYW7qDQiZ) : boîtes chinoise et thaïe empilées qui se chevauchent verticalement
    boxes = [
        TextBox("没钱没关系", 1.0, (320, 250, 760, 345)),
        TextBox("laiatiulahiuls", 0.74, (270, 330, 810, 445)),
        TextBox("如奇心大品行", 0.49, (250, 430, 840, 550)),
    ]
    lines = boxes_to_lines(boxes, min_score=0.5, min_cjk_ratio=0.5)
    assert [ln.text for ln in lines] == ["没钱没关系", "laiatiulahiuls", "如奇心大品行"]
    assert lines[0].is_chinese and not lines[2].is_chinese


def test_blocks_and_neighbour_expansion() -> None:
    l1 = TextLine("錢不是萬能的", 0.9, (200, 140, 500, 180), True)
    l2 = TextLine("但沒有錢是萬萬不能的", 0.9, (100, 190, 600, 230), True)
    far = TextLine("標題", 0.9, (200, 900, 300, 940), True)
    blocks = group_blocks([l1, l2, far])
    assert sorted(len(b) for b in blocks) == [1, 2]
    thai = TextLine("ปัญหา", 0.5, (220, 240, 480, 270), False)
    disc = TextLine("O", 0.9, (250, 280, 500, 520), False)  # objet de la scène lu comme une lettre
    assert expand_with_neighbours((100, 140, 600, 230), [thai, disc], line_height=40) == (100, 140, 600, 270)
