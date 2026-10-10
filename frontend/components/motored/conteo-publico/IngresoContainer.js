'use client';

/**
 * Join logic: the 6-digit code plus two members (name and cédula). The
 * cédulas live only in this component's state and the join request; after
 * the join only the device token, the pair label and the store are kept.
 */
import { useMemo, useState } from 'react';
import { esErrorDeRed, unirse } from '../../../lib/motored/conteoPublicoApi';
import { leerCola, lecturasPendientes } from '../../../lib/motored/conteoCola';
import IngresoPareja from './IngresoPareja';
import { TEXTOS } from './textos';

const VACIO = { nombre: '', cedula: '' };

function validar(codigo, integrantes) {
  if (!/^\d{6}$/.test(codigo)) return 'Escriba el código del conteo: 6 números.';
  if (integrantes.some((i) => i.nombre.trim().length < 2)) return 'Escriba el nombre completo de cada integrante.';
  if (integrantes.some((i) => i.cedula.length < 4 || i.cedula.length > 20)) {
    return 'La cédula debe tener entre 4 y 20 números.';
  }
  if (integrantes[0].cedula === integrantes[1].cedula) return 'Las cédulas de los integrantes deben ser distintas.';
  return null;
}

function mensajeError(error) {
  if (esErrorDeRed(error)) return TEXTOS.sinConexionIngreso;
  if (error.status === 429) return TEXTOS.bloqueado;
  if (error.status === 401) return TEXTOS.accesoInvalido;
  return error.message || 'No se pudo ingresar. Intente de nuevo.';
}

function dispositivo() {
  return typeof window !== 'undefined' && window.innerWidth < 600 ? 'MOVIL' : 'ESCRITORIO';
}

export default function IngresoContainer({ slug, aviso, onIngreso }) {
  const [codigo, setCodigo] = useState('');
  const [integrantes, setIntegrantes] = useState([VACIO, VACIO]);
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const huerfanas = useMemo(() => lecturasPendientes(leerCola(slug).items), [slug]);

  const cambiarIntegrante = (indice, campo, valor) => {
    const limpio = campo === 'cedula' ? valor.replace(/\D/g, '').slice(0, 20) : valor;
    setIntegrantes((actual) => actual.map((i, n) => (n === indice ? { ...i, [campo]: limpio } : i)));
  };

  const enviar = async (e) => {
    e.preventDefault();
    const problema = validar(codigo, integrantes);
    if (problema) {
      setError(problema);
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      const r = await unirse(slug, {
        codigo,
        dispositivo: dispositivo(),
        integrantes: integrantes.map((i) => ({ nombre: i.nombre.trim(), cedula: i.cedula })),
      });
      onIngreso({
        token: r.sesion_token, sesionId: r.sesion_id, etiqueta: r.etiqueta, sucursal: r.sucursal,
        esPrueba: Boolean(r.es_prueba),
      });
    } catch (fallo) {
      setError(mensajeError(fallo));
      setEnviando(false);
    }
  };

  return (
    <IngresoPareja
      codigo={codigo}
      integrantes={integrantes}
      error={error}
      aviso={aviso}
      huerfanas={huerfanas}
      enviando={enviando}
      onCodigo={(valor) => setCodigo(valor.replace(/\D/g, '').slice(0, 6))}
      onIntegrante={cambiarIntegrante}
      onEnviar={enviar}
    />
  );
}
