from vendors import jbl
from tests.fakes import FakeDev

M = jbl.MODELS[0]


def test_ligado():
    h = FakeDev(replies=[[0x68, 1], [0x49, 75]])
    assert jbl.read(h, M) == (75, False) and h.writes == [] and h.features == []


def test_desligado():
    assert jbl.read(FakeDev(replies=[[0x68, 0]]), M) is None


def test_sem_eco_do_id_da_none():
    assert jbl.read(FakeDev(replies=[[0x67, 1], [0x49, 75]]), M) is None


def test_sem_resposta_da_none():
    assert jbl.read(FakeDev(), M) is None
