# Datos Historicos

## Ubicacion

```
C:\Users\Pablo Nieto\Desktop\PopFinance\data_futuros\
```

Esta ruta se pasa al motor con el argumento `--hist-data-path`.

## Instrumentos disponibles

| Simbolo | Nombre | Exchange | Multiplicador | Tick minimo |
|---------|--------|----------|---------------|-------------|
| @ES | S&P 500 E-mini | CME | 50 | 0.25 |
| @MES | Micro E-mini S&P 500 | CME | 5 | 0.25 |
| @NQ | Nasdaq 100 E-mini | CME | 20 | 0.25 |
| @MNQ | Micro Nasdaq 100 | CME | 2 | 0.25 |
| @GC | Gold Futures | COMEX | 100 | 0.10 |
| @MGC | Micro Gold Futures | COMEX | 10 | 0.10 |

## Ficheros

Cada instrumento tiene dos variantes:

| Fichero | Descripcion |
|---------|-------------|
| `@ES_1M.txt` | Datos crudos a 1 minuto |
| `@ES_1M_edit.txt` | Datos limpios a 1 minuto (preferido) |

**Usa siempre la variante `_edit`** (datos limpiados). Los ficheros sin `_edit` son los datos crudos originales y pueden tener inconsistencias.

## Formato

CSV con las siguientes columnas:

```
date,time,open,high,low,close,vol
```

Ejemplo:

```
2020-01-02,09:30,3258.25,3259.00,3257.50,3258.75,1523
2020-01-02,09:31,3258.75,3260.00,3258.50,3259.75,892
```

- `date`: YYYY-MM-DD
- `time`: HH:MM
- `open`, `high`, `low`, `close`: precios OHLC
- `vol`: volumen de la vela

## Resampleo

El motor trabaja internamente con datos de 1 minuto y los resamplea a la frecuencia que necesite cada estrategia:

- **1H** (1 hora)
- **4H** (4 horas)
- **8H** (8 horas)
- **1D** (1 dia)
- **1W** (1 semana)

No necesitas preparar datos en otros timeframes; el motor se encarga de todo a partir de los ficheros de 1 minuto.

## Correspondencia simbolo-fichero

El motor mapea el `symbol` de la estrategia al fichero correspondiente. Por ejemplo, una estrategia con `"symbol": "MES"` busca el fichero `@MES_1M_edit.txt` en el directorio de datos historicos.
