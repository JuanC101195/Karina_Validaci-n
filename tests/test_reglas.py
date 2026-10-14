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
    assert filas["JP"]["G"] == 185 and filas["JP"]["M"] == 35
    assert filas["RC"]["H"] == 225 and filas["RC"]["N"] == 25 and filas["RC"]["V"] == 10


def test_pronto_va_a_columna_y():
    # 10-oct-2026: pronto de JP llega en un registro aparte (MOTOHOY)
    filas, _ = reglas.agrupar_recaudo([reg("JP", "MOTOHOY", pronto=13581)])
    assert filas["JP"]["Y"] == 13581


def test_registro_desconocido_va_a_avisos_no_se_pierde():
    filas, avisos = reglas.agrupar_recaudo([reg("XX", "FAVIPAN", abono=100), reg("JP", "NUEVA", abono=50)])
    assert len(avisos) == 2
    assert sum(filas["JP"].values()) == 0


def test_transferencia_se_avisa():
    _, avisos = reglas.agrupar_recaudo([reg("JP", "FAVIPAN", abono=10, transf=5)])
    assert any("Transferencia" in a for a in avisos)


def caja3(**kw):
    base = {"ajustes": 0.0, "pronto": 0.0, "alquiler": 0.0, "traslado": 0.0,
            "gastos": 0.0, "retiro": 0.0, "saldo": 0.0, "saldo_caja3": 0.0}
    base.update(kw)
    return base


def test_caja3_dia_normal_alquiler_va_a_ab():
    # RC 7-oct-2026: alquiler 16280 -> AB
    cols, comite = reglas.fila_desde_caja3(caja3(alquiler=16280, traslado=12600, ajustes=25))
    assert not comite
    assert cols["AB"] == 16280 and cols["AC"] == 0 and cols["Z"] == 12600 and cols["AA"] == 25


def test_caja3_dia_comite_alquiler_va_a_motos_comite():
    # JP 9-oct-2026: alquiler 48840 -> AC, retiro pablo 75852 -> AE
    cols, comite = reglas.fila_desde_caja3(caja3(alquiler=48840, gastos=51768, retiro=75852))
    assert comite
    assert cols["AB"] == 0 and cols["AC"] == 48840 and cols["AD"] == 51768 and cols["AE"] == 75852


def test_comparar_detecta_saldo_caja3_mal_digitado():
    # JP 10-oct-2026: el rojo de 1.001
    difs = reglas.comparar({"AJ": 6764386.47}, {"AJ": 6765387.47})
    assert len(difs) == 1 and difs[0]["diferencia"] == 1001.0


def test_comparar_celda_vacia_con_esperado_cero_no_es_diferencia():
    assert reglas.comparar({"AB": 0.0}, {"AB": None}) == []


def test_comparar_celda_vacia_con_valor_esperado_si_es_diferencia():
    difs = reglas.comparar({"AG": 50488.88}, {"AG": None})
    assert difs[0]["excel"] is None


def test_pronto_distinto_entre_fuentes():
    assert reglas.pronto_caja3_vs_sistema(-200, 0) is not None
    assert reglas.pronto_caja3_vs_sistema(13581, 13581) is None
