import pytest

from karina import reglas


def reg(cobro, empresa, abono=0, multa=0, repuesto=0, pronto=0, transf=0):
    return {"COBRO": cobro, "empresa": empresa, "abono": abono, "multa": multa,
            "repuesto": repuesto, "prestamo": repuesto, "pronto": pronto,
            "transf": transf, "neto": abono + multa + repuesto}


def test_hoja_de_cobro():
    assert reglas.hoja_de_cobro("JP") == "JP"
    assert reglas.hoja_de_cobro("JP11") == "JP"
    assert reglas.hoja_de_cobro("Ricar") == "RC"
    assert reglas.hoja_de_cobro("RC3") == "RC"
    assert reglas.hoja_de_cobro("JPX") is None
    assert reglas.hoja_de_cobro(None) is None


def test_agrupar_suma_rutas_en_la_hoja_del_socio():
    # JP FAVIPAN 13-oct-2026: JP 4040 + JP10 430 + JP11 175 = 4645
    filas, avisos = reglas.agrupar_recaudo([
        reg("JP", "FAVIPAN", abono=4040, multa=125),
        reg("JP10", "FAVIPAN", abono=430, multa=25),
        reg("JP11", "FAVIPAN", abono=175, multa=35),
    ])
    assert filas["JP"]["C"] == 4645
    assert filas["JP"]["I"] == 185
    assert filas["RC"]["C"] == 0
    assert avisos == []


def test_agrupar_columnas_india_y_motohoy():
    filas, _ = reglas.agrupar_recaudo([
        reg("JP", "ALMACEN DE REPUESTOS", abono=185, multa=35),
        reg("Ricar", "MOTOHOY", abono=225, multa=25, repuesto=10),
    ])
    assert filas['JP']['G'] == 185
    assert filas['JP']['M'] == 35
    assert filas['RC']['H'] == 225
    assert filas['RC']['N'] == 25
    assert filas['RC']['V'] == 10


def test_pronto_va_a_columna_y():
    # 10-oct-2026: pronto de JP llega en un registro aparte (MOTOHOY)
    filas, _ = reglas.agrupar_recaudo([reg("JP", "MOTOHOY", pronto=13581)])
    assert filas["JP"]["Y"] == 13581


def test_registro_desconocido_va_a_avisos_no_se_pierde():
    filas, avisos = reglas.agrupar_recaudo([reg("XX", "FAVIPAN", abono=100), reg("JP", "NUEVA", abono=50)])
    assert len(avisos) == 2
    assert sum(filas["JP"].values()) == 0


def test_transferencia_se_suma_al_recaudo_del_punto():
    filas, avisos = reglas.agrupar_recaudo([reg("JP", "FAVIPAN", abono=10, transf=5)])
    assert filas['JP']['C'] == 15
    assert avisos == []


def caja3(**kw):
    base = {"ajustes": 0.0, "ajustes_multas": 0.0, "pronto": 0.0, "alquiler": 0.0, "traslado": 0.0,
            "gastos": 0.0, "retiro": 0.0, "saldo": 0.0, "saldo_caja3": 0.0}
    base.update(kw)
    return base


def test_caja3_dia_normal_alquiler_va_a_ab():
    # RC 7-oct-2026: alquiler 16280 -> AB
    cols, comite, pendiente = reglas.fila_desde_caja3(caja3(alquiler=16280, traslado=12600, ajustes=25))
    assert not comite
    assert not pendiente
    assert cols['AB'] == 16280
    assert cols['AC'] == 0
    assert cols['Z'] == 12600
    assert cols['AA'] == 25


def test_caja3_dia_comite_sin_respuesta_queda_pendiente():
    # JP 9-oct-2026: alquiler 48840 de Caja 3 = alquiler + inversion en motos
    cols, comite, pendiente = reglas.fila_desde_caja3(caja3(alquiler=48840, gastos=51768, retiro=75852))
    assert comite
    assert pendiente
    assert 'AB' not in cols
    assert 'AC' not in cols
    assert cols['AD'] == 51768
    assert cols['AE'] == 75852


def test_caja3_dia_comite_con_alquiler_total_separa_la_inversion():
    # RC 21-ago-2026: Caja 3 110540 = alquiler 28580 + inversion 81960
    cols, comite, pendiente = reglas.fila_desde_caja3(caja3(alquiler=110540, gastos=1, retiro=1), 28580)
    assert comite
    assert not pendiente
    assert cols['AB'] == 28580
    assert cols['AC'] == 81960


def test_caja3_dia_comite_sin_alquiler_no_pregunta():
    cols, comite, pendiente = reglas.fila_desde_caja3(caja3(gastos=100, retiro=50))
    assert comite
    assert not pendiente
    assert cols['AB'] == 0
    assert cols['AC'] == 0


def test_comparar_detecta_saldo_caja3_mal_digitado():
    # JP 10-oct-2026: el rojo de 1.001
    difs = reglas.comparar({"AJ": 6764386.47}, {"AJ": 6765387.47})
    assert len(difs) == 1
    assert difs[0]['diferencia'] == 1001.0


def test_comparar_celda_vacia_con_esperado_cero_no_es_diferencia():
    assert reglas.comparar({"AB": 0.0}, {"AB": None}) == []


def test_comparar_celda_vacia_con_valor_esperado_si_es_diferencia():
    difs = reglas.comparar({"AG": 50488.88}, {"AG": None})
    assert difs[0]["excel"] is None


def test_pronto_distinto_entre_fuentes():
    assert reglas.pronto_caja3_vs_sistema(-200, 0) is not None
    assert reglas.pronto_caja3_vs_sistema(13581, 13581) is None


def test_acumulado_multas_incluye_india_mh_y_ajustes():
    # JP 13-oct-2026: O480=2085; I..N = 185+315+90+605+35+25, P=0
    esp = {"I": 185, "J": 315, "K": 90, "L": 605, "M": 35, "N": 25}
    assert reglas.acumulado_esperado("O", esp, 0, 2085, reinicio=False) == 3340
    assert reglas.acumulado_esperado("O", esp, 20, 2085, reinicio=True) == 1275


def test_acumulado_repuestos_incluye_india_y_mh():
    esp = {"Q": 10, "R": 20, "S": 0, "T": 5, "U": 1, "V": 155.5}
    assert reglas.acumulado_esperado("W", esp, 999, 100, reinicio=False) == 291.5


def test_reinicio_por_formula():
    assert reglas.es_reinicio("=SUM(I479:L479,P479)", "O", 479)
    assert not reglas.es_reinicio("=SUM(I481:L481,P481)+O480", "O", 481)


def test_formula_correcta_no_avisa():
    assert reglas.revisar_formula_acumulado("O", "=SUM(I481:N481,P481)+O480", 481) == []
    assert reglas.revisar_formula_acumulado("O", "=SUMA(I479:N479;P479)", 479) == []
    assert reglas.revisar_formula_acumulado("W", "=SUM(Q481:V481)+W480", 481) == []


def test_formula_que_deja_fuera_india_mh_avisa():
    avisos = reglas.revisar_formula_acumulado("O", "=SUM(I481:L481,P481)+O480", 481)
    assert len(avisos) == 1
    assert 'distinta' in avisos[0]


def test_numero_escrito_a_mano_en_formula_avisa():
    # JP W476 real: =SUM(Q476:U476)+W475-155.5
    avisos = reglas.revisar_formula_acumulado("W", "=SUM(Q476:U476)+W475-155.5", 476)
    assert any("-155.5" in a for a in avisos)


def test_valor_fijo_en_lugar_de_formula_avisa():
    assert reglas.revisar_formula_acumulado("O", 3280, 481)


def test_formula_de_reinicio_sugiere_sin_acumulado_anterior():
    # JP O479 (sabado 10-oct, reinicio): =SUM(I479:L479,P479)
    avisos = reglas.revisar_formula_acumulado("O", "=SUM(I479:L479,P479)", 479)
    assert avisos
    assert avisos[0].endswith('=SUM(I479:N479,P479)')


def test_ajustes_multas_van_a_p_y_cuotas_a_aa():
    # JP 3-oct-2026: Caja 3 E=-25 (cuotas) F=25 (multas)
    cols, _, _ = reglas.fila_desde_caja3(caja3(ajustes=-25, ajustes_multas=25))
    assert cols['AA'] == -25
    assert cols['P'] == 25


def test_acumulado_usa_p_de_caja3_si_existe():
    esp = {"I": 100, "P": 25}
    assert reglas.acumulado_esperado("O", esp, 999, 0, reinicio=True) == 125


def test_redondeo_a_enteros_no_es_diferencia():
    # JP 11-sep-2026: AD 65131 en CONTABILIDAD vs 65131.84 de Caja 3
    assert reglas.comparar({"AD": 65131.84}, {"AD": 65131.0}) == []
    assert len(reglas.comparar({"AD": 65133.0}, {"AD": 65131.0})) == 1


def test_leer_monto_formato_colombiano():
    assert reglas.leer_monto("15.980") == 15980
    assert reglas.leer_monto("15980") == 15980
    assert reglas.leer_monto("1.234,5") == 1234.5
    assert reglas.leer_monto("155,5") == 155.5
    assert reglas.leer_monto("155.5") == 155.5
    assert reglas.leer_monto("$ 28.580") == 28580
    assert reglas.leer_monto("0") == 0
    with pytest.raises(ValueError):
        reglas.leer_monto("abc")
