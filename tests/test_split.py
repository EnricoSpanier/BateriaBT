import bateria_bt as b


def test_padrao_lado_a_lado_a_partir_da_posicao_do_widget():
    # da esquerda para a direita: o último fica na posição do widget único
    assert b.default_offsets(100, [50, 30, 20]) == [100 + 30 + 20 + 8, 100 + 20 + 4, 100]
    assert b.default_offsets(0, [40]) == [0]
