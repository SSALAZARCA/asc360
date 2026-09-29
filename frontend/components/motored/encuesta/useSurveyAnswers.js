import { useState } from 'react';
import { MATRIX_ROWS } from './copy';

/** The customer's answers to Q1..Q4 (pure form state, no navigation or API). */
export default function useSurveyAnswers() {
  const [q1, setQ1] = useState(null);
  const [matrix, setMatrix] = useState(Array(MATRIX_ROWS.length).fill(null));
  const [observaciones, setObservaciones] = useState('');
  const [consent, setConsent] = useState(null);
  const answerMatrix = (index, value) =>
    setMatrix((current) => current.map((a, j) => (j === index ? value : a)));
  return { q1, setQ1, matrix, answerMatrix, observaciones, setObservaciones, consent, setConsent };
}
