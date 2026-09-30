'use client';
/** State/effects for the survey admin page (container logic). */
import { useCallback, useEffect, useState } from 'react';
import {
  descargarPlantillaEncuesta, validarCargaEncuesta, guardarCargaEncuesta, listCargasEncuesta,
} from '../../../lib/motored/encuestaCargasApi';

export default function useEncuestaAdmin() {
  const [file, setFile] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [validatedFile, setValidatedFile] = useState(null);
  const [guardado, setGuardado] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [cargas, setCargas] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState('');

  const loadList = useCallback(async () => {
    setListError('');
    try {
      setCargas(await listCargasEncuesta());
    } catch (err) {
      setListError(err.message || 'No se pudo cargar el historial.');
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  const run = async (fn) => {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (err) {
      setError(err.message || 'Ocurrió un error. Intenta de nuevo.');
    } finally {
      setBusy(false);
    }
  };

  const actions = {
    downloadTemplate: () => run(descargarPlantillaEncuesta),
    pickFile: (f) => {
      setFile(f);
      setResultado(null);
      setValidatedFile(null);
      setGuardado(null);
      setError('');
    },
    validate: () => run(async () => {
      const res = await validarCargaEncuesta(file);
      setResultado(res);
      setValidatedFile(res.ok ? file : null);
      setGuardado(null);
    }),
    save: () => run(async () => {
      const res = await guardarCargaEncuesta(file);
      if (!res.ok) {
        setResultado(res);
        setValidatedFile(null);
        return;
      }
      setGuardado(res);
      setValidatedFile(null);
      await loadList();
    }),
  };

  const canSave = Boolean(file) && validatedFile === file && !busy;
  return {
    state: { file, resultado, guardado, busy, error, canSave },
    actions,
    list: { cargas, loading: loadingList, error: listError },
  };
}
