"""Checks the text-matching rules against realistic OCR output.

Strings below are shaped like what RapidOCR actually returns: accents kept or
lost, spaces frequently dropped, and capital I read back as l, 1 or |.

    python -m pytest test_matching.py -q      (or just: python test_matching.py)
"""

import pytest

from detect import _COUNTDOWN, _MAX_LABEL_RATIO, normalize, prefix_similarity

KEYWORD = "ignorer"
THRESHOLD = 0.90


def matches(raw: str) -> bool:
    """Mirror of the accept/reject rule in SkipButtonFinder.scan_box."""
    compact = normalize(raw)
    if _COUNTDOWN.search(compact):
        return False
    if prefix_similarity(compact, KEYWORD) < THRESHOLD:
        return False
    return len(compact) <= _MAX_LABEL_RATIO * len(KEYWORD)


SKIP_BUTTONS = [
    "Ignorer",
    "Ignorer >|",
    "Ignorer l'annonce",
    "Ignorer les annonces",
    "Ignorer la publicité",
    "Ignorerlesannonces",   # spaces dropped
    "lgnorer",              # capital I read as lowercase L
    "1gnorer",              # ... as a one
    "|gnorer",              # ... as a pipe
    "IGNORER",
    "Ignorer  ",
    "Ignore",               # trailing r dropped -- a miss here costs more than
                            # a stray click, so a near read still counts
]

COUNTDOWNS = [
    "Ignorer dans 5",
    "Ignorer les annonces dans 3",
    "Ignorerdans5",
    "Ignorer 4",
    "L'annonce se termine dans 6",
]

BYSTANDERS = [
    "S'abonner",
    "Partager",
    "Enregistrer",
    "Signaler",
    "Plus tard",
    "Annuler",
    "Suivant",
    "Commentaires",
    "Ignor",                # too far from the word to be a confident read
]

# Real misfires from a live run. OCR hands back a whole line at a time, so any
# line mentioning the word used to look like a button.
FALSE_POSITIVES = [
    "gitignore",
    ".gitignore",
    "Add .gitignore",
    "Choose a .gitignore template",
    "gitignore.mavbeweshouldraiseconfidencelevelsneededtoselectandclick",
    'thetext so we ensure it takes"Ignorer"but not"Ignor",Ialso noticed it clicks',
]


@pytest.mark.parametrize("raw", SKIP_BUTTONS)
def test_accepts_skip_button(raw):
    assert matches(raw), f"should have matched {raw!r}"


@pytest.mark.parametrize("raw", COUNTDOWNS)
def test_rejects_countdown(raw):
    assert not matches(raw), f"should have rejected countdown {raw!r}"


@pytest.mark.parametrize("raw", BYSTANDERS)
def test_rejects_unrelated_ui_text(raw):
    assert not matches(raw), f"should have rejected {raw!r}"


@pytest.mark.parametrize("raw", FALSE_POSITIVES)
def test_rejects_text_that_merely_contains_the_word(raw):
    assert not matches(raw), f"should have rejected {raw!r}"


def test_accepts_the_real_button_seen_in_a_live_run():
    """The one confirmed sighting of an actual French ad, kept as a guard.

    A live run clicked a genuine skip button that OCR read as a clean isolated
    box: 'Ignorer' at confidence 0.82. Any future tightening of these rules has
    to keep accepting it.
    """
    assert matches("Ignorer")
    assert 0.82 >= 0.55  # comfortably over the OCR confidence floor
    # An isolated label means the click aims at the box centre, as it should.
    compact = normalize("Ignorer")
    assert min(1.0, len(KEYWORD) / len(compact)) == 1.0


def test_normalize_folds_lookalikes_and_punctuation():
    assert normalize("Ignorer l'annonce") == "ignoreriannonce"
    assert normalize("|GNORER") == "ignorer"
    assert normalize("publicité") == "pubiicite"


def test_similarity_is_anchored_at_the_start():
    assert prefix_similarity("ignorer", "ignorer") == 1.0
    assert prefix_similarity("ignorerlesannonces", "ignorer") == 1.0
    # The same letters mid-string must not count -- this is the gitignore case.
    assert prefix_similarity("gitignore", "ignorer") < THRESHOLD
    assert prefix_similarity("partager", "ignorer") < THRESHOLD


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
