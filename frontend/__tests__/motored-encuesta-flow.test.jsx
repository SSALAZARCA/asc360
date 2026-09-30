/**
 * Public satisfaction survey page: full flow against a mocked fetch.
 * Question texts are asserted verbatim (they mirror the Google Form).
 */
import { render, screen, within, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import EncuestaPage from '../app/motored/encuesta/page';

const Q1 =
  'En una calificación de 1 a 5, donde 5 es "Muy Satisfecho" y 1 es "Muy Insatisfecho", en general, ¿qué tan satisfecho se siente usted con el servicio de posventa recibida por el taller?';
const Q2_INTRO =
  'Pensando en su experiencia en el taller al que asistió, por favor califique utilizando la misma escala de 1 a 5, donde 5 es "excelente" y 1 es "pésimo", como califica usted:';
const Q2_ROWS = [
  'La explicación y asesoría técnica que le dieron en el taller de los problemas que tenía la moto',
  'La confianza en la reparación de la motocicleta realizada por el taller o centro de servicio',
  'Servicio que le prestaron en el taller o centro de servicio',
  'La calidad del trabajo realizado por los mecánicos',
  'La claridad en la explicación recibida de los cobros realizados antes y después del servicio',
  'La confianza en la procedencia y originalidad de los repuestos',
];
const Q3 = '¿Qué observaciones tiene respecto al servicio que obtuvo en el taller?';
const Q4 =
  'PHD2. Dando cumplimiento a la ley de Protección de Datos Personales le solicito su autorización para que Motos red Nacional pueda contactarlo nuevamente en caso de ser necesario con fines de supervisión de esta encuesta y futuras encuestas. ¿Está usted de acuerdo?';
const NOT_FOUND =
  'No encontramos tus datos. Revisa la cédula de la persona a cuyo nombre está registrada la motocicleta y los últimos 4 dígitos del celular donde te llegó el mensaje.';
const LAST4_LABEL = 'Últimos 4 dígitos de tu celular';

const REG_A = { registro_id: 'reg-a', placa: 'ABC12D', linea: 'Xpulse 200' };
const REG_B = { registro_id: 'reg-b', placa: 'XYZ98E', linea: 'Hunk 160' };

function reply(status, body) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => body });
}

function setupFetch({ identificar, respuestas }) {
  global.fetch = jest.fn((url, opts) => {
    if (String(url).endsWith('/encuesta/publico/identificar')) return identificar(opts);
    if (String(url).endsWith('/encuesta/publico/respuestas')) return respuestas(opts);
    return reply(500, {});
  });
}

const pendiente = (registros = [REG_A]) =>
  reply(200, { estado: 'PENDIENTE', primer_nombre: 'Juan', registros });

const submitCalls = () =>
  global.fetch.mock.calls.filter(([url]) => String(url).endsWith('/respuestas'));

let user;
beforeEach(() => {
  jest.useFakeTimers();
  user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
});
afterEach(() => {
  jest.useRealTimers();
  delete global.fetch;
});

async function identify(cedula = '1010', last4 = '2233') {
  await user.type(screen.getByLabelText('Ingresa tu número de cédula'), cedula);
  await user.type(screen.getByLabelText(LAST4_LABEL), last4);
  await user.click(screen.getByRole('button', { name: 'Continuar' }));
}

async function answerMatrix(skipLast = false) {
  for (let i = 0; i < 6; i += 1) {
    const group = screen.getByRole('radiogroup', { name: Q2_ROWS[i] });
    if (skipLast && i === 5) {
      await user.click(within(group).getByRole('radio', { name: 'NS/NR' }));
    } else {
      await user.click(within(group).getByRole('radio', { name: String(Math.min(i + 1, 5)) }));
    }
  }
}

async function reachQ4() {
  await identify();
  await user.click(await screen.findByRole('radio', { name: '2' }));
  await user.click(screen.getByRole('button', { name: 'Continuar' }));
  await answerMatrix(true);
  await user.click(screen.getByRole('button', { name: 'Continuar' }));
  await user.type(screen.getByLabelText(Q3), 'Todo bien');
  await user.click(screen.getByRole('button', { name: 'Continuar' }));
}

describe('cédula screen', () => {
  it('shows the verbatim intro, question and hint', () => {
    render(<EncuestaPage />);
    expect(
      screen.getByText(
        'En estos momentos estamos haciendo un estudio sobre la satisfacción del servicio de posventa prestado en nuestros talleres.'
      )
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Ingresa tu número de cédula')).toHaveAttribute('inputmode', 'numeric');
    expect(
      screen.getByText('La cédula de la persona a cuyo nombre está registrada la motocicleta.')
    ).toBeInTheDocument();
    expect(screen.getByText('ENCUESTA DE SATISFACCIÓN')).toBeInTheDocument();
  });

  it('shows the celular last-4 field with its hint, numeric and capped at 4 digits', async () => {
    render(<EncuestaPage />);
    const field = screen.getByLabelText(LAST4_LABEL);
    expect(field).toHaveAttribute('inputmode', 'numeric');
    expect(field).toHaveAttribute('maxlength', '4');
    expect(screen.getByText('Los del número donde te llegó el mensaje de WhatsApp.')).toBeInTheDocument();
    await user.type(field, 'a1b2c3d4e5');
    expect(field).toHaveValue('1234');
  });

  it('keeps Continuar disabled until cédula and exactly 4 celular digits are typed', async () => {
    render(<EncuestaPage />);
    const cta = screen.getByRole('button', { name: 'Continuar' });
    await user.type(screen.getByLabelText('Ingresa tu número de cédula'), '1010');
    expect(cta).toBeDisabled();
    await user.type(screen.getByLabelText(LAST4_LABEL), '223');
    expect(cta).toBeDisabled();
    await user.type(screen.getByLabelText(LAST4_LABEL), '3');
    expect(cta).toBeEnabled();
    await user.clear(screen.getByLabelText('Ingresa tu número de cédula'));
    expect(cta).toBeDisabled();
  });

  it('keeps Continuar disabled until a cédula is typed', async () => {
    render(<EncuestaPage />);
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeDisabled();
  });

  it('NO_ENCONTRADA shows the backend message as an alert and allows retry', async () => {
    setupFetch({ identificar: () => reply(200, { estado: 'NO_ENCONTRADA', mensaje: NOT_FOUND }) });
    render(<EncuestaPage />);
    await identify();
    expect(await screen.findByRole('alert')).toHaveTextContent(NOT_FOUND);
    expect(screen.getByLabelText('Ingresa tu número de cédula')).toBeInTheDocument();
    expect(global.fetch.mock.calls[0][1].body).toBe(JSON.stringify({ cedula: '1010', celular_ultimos4: '2233' }));
  });

  it('YA_RESPONDIDA shows the thank-you with the date', async () => {
    setupFetch({
      identificar: () => reply(200, { estado: 'YA_RESPONDIDA', respondida_at: '2026-09-28T15:30:00' }),
    });
    render(<EncuestaPage />);
    await identify();
    expect(await screen.findByText('Ya recibimos tu calificación.')).toBeInTheDocument();
    expect(screen.getByText('Gracias por el tiempo que nos diste el 28 de septiembre.')).toBeInTheDocument();
  });

  it('PENDIENTE with one record greets and goes straight to Q1', async () => {
    setupFetch({ identificar: () => pendiente() });
    render(<EncuestaPage />);
    await identify();
    expect(await screen.findByText('Hola, Juan.')).toBeInTheDocument();
    expect(screen.getByText(Q1)).toBeInTheDocument();
    expect(screen.getByText('PREGUNTA 1 DE 4')).toBeInTheDocument();
    expect(screen.queryByText('¿Sobre cuál moto nos cuentas?')).not.toBeInTheDocument();
  });

  it('PENDIENTE with several records shows the placa picker', async () => {
    setupFetch({ identificar: () => pendiente([REG_A, REG_B]) });
    render(<EncuestaPage />);
    await identify();
    expect(await screen.findByText('¿Sobre cuál moto nos cuentas?')).toBeInTheDocument();
    expect(screen.getByText('Hola, Juan.')).toBeInTheDocument();
    expect(screen.getByText('ABC12D')).toBeInTheDocument();
    expect(screen.getByText('Hunk 160')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /XYZ98E/ }));
    expect(screen.getByText(Q1)).toBeInTheDocument();
  });

  it('HTTP 429 shows the rate-limit message', async () => {
    setupFetch({ identificar: () => reply(429, { detail: 'rate' }) });
    render(<EncuestaPage />);
    await identify();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Hiciste demasiados intentos. Espera un minuto e inténtalo de nuevo.'
    );
  });

  it('network error shows a retry message', async () => {
    setupFetch({ identificar: () => Promise.reject(new TypeError('failed')) });
    render(<EncuestaPage />);
    await identify();
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos conectarnos');
  });

  it('shows the offline banner when the browser goes offline', async () => {
    render(<EncuestaPage />);
    act(() => {
      window.dispatchEvent(new Event('offline'));
    });
    expect(screen.getByText('Se perdió la conexión.')).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    expect(screen.queryByText('Se perdió la conexión.')).not.toBeInTheDocument();
  });
});

describe('Q1 scale', () => {
  beforeEach(async () => {
    setupFetch({ identificar: () => pendiente() });
    render(<EncuestaPage />);
    await identify();
    await screen.findByText(Q1);
  });

  it('is a radiogroup with end labels and disabled CTA until answered', () => {
    expect(screen.getByRole('radiogroup', { name: Q1 })).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(5);
    expect(screen.getByText('MUY INSATISFECHO')).toBeInTheDocument();
    expect(screen.getByText('MUY SATISFECHO')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeDisabled();
  });

  it('selects with click, shows the word and supports arrow keys', async () => {
    await user.click(screen.getByRole('radio', { name: '4' }));
    expect(screen.getByRole('radio', { name: '4' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('Satisfecho')).toBeInTheDocument();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: '5' })).toHaveAttribute('aria-checked', 'true');
    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(screen.getByRole('radio', { name: '3' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeEnabled();
  });

  it('Atrás from Q1 returns to the cédula screen', async () => {
    await user.click(screen.getByRole('button', { name: 'Atrás' }));
    expect(screen.getByLabelText('Ingresa tu número de cédula')).toBeInTheDocument();
  });
});

describe('Q2 matrix', () => {
  beforeEach(async () => {
    setupFetch({ identificar: () => pendiente() });
    render(<EncuestaPage />);
    await identify();
    await user.click(await screen.findByRole('radio', { name: '3' }));
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
  });

  it('shows verbatim intro, six rows, legend and gates the CTA', async () => {
    expect(screen.getByText(Q2_INTRO)).toBeInTheDocument();
    Q2_ROWS.forEach((row) => expect(screen.getByText(row)).toBeInTheDocument());
    expect(screen.getByText('1 Pésimo · 5 Excelente')).toBeInTheDocument();
    expect(screen.getByText('PREGUNTA 2 DE 4')).toBeInTheDocument();
    expect(screen.getByText('0/6')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Faltan 6 de 6' })).toBeDisabled();
    const group = screen.getByRole('radiogroup', { name: Q2_ROWS[0] });
    await user.click(within(group).getByRole('radio', { name: '5' }));
    expect(screen.getByRole('button', { name: 'Faltan 5 de 6' })).toBeDisabled();
    expect(screen.getByText('1/6')).toBeInTheDocument();
  });

  it('counts NS/NR as answered', async () => {
    await answerMatrix(true);
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeEnabled();
  });
});

describe('Q3 observaciones', () => {
  beforeEach(async () => {
    setupFetch({ identificar: () => pendiente() });
    render(<EncuestaPage />);
    await identify();
    await user.click(await screen.findByRole('radio', { name: '3' }));
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    await answerMatrix();
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
  });

  it('is optional, has a counter and a 2000 char limit', async () => {
    const box = screen.getByLabelText(Q3);
    expect(box).toHaveAttribute('maxlength', '2000');
    expect(box).toHaveAttribute('rows', '6');
    expect(screen.getByText('0 / 2000')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Seguir sin escribir' })).toBeEnabled();
    await user.click(box);
    await user.paste('hola');
    expect(screen.getByText('4 / 2000')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeInTheDocument();
  });

  it('skipping goes to the consent question', async () => {
    await user.click(screen.getByRole('button', { name: 'Seguir sin escribir' }));
    expect(screen.getByText(Q4)).toBeInTheDocument();
    expect(screen.getByText('PREGUNTA 4 DE 4')).toBeInTheDocument();
  });
});

describe('Q4 consent and submit', () => {
  it('auto-advances on Sí and submits the exact payload', async () => {
    setupFetch({
      identificar: () => pendiente(),
      respuestas: () => reply(200, { clasificacion: 'DETRACTOR', caso_numero: 42, primer_nombre: 'Juan' }),
    });
    render(<EncuestaPage />);
    await reachQ4();
    expect(screen.getByText(Q4)).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Sí' }));
    expect(submitCalls()).toHaveLength(0);
    await act(async () => {
      jest.advanceTimersByTime(250);
    });
    await waitFor(() => expect(submitCalls()).toHaveLength(1));
    expect(JSON.parse(submitCalls()[0][1].body)).toEqual({
      cedula: '1010',
      celular_ultimos4: '2233',
      registro_id: 'reg-a',
      satisfaccion_general: 2,
      p_explicacion_tecnica: 1,
      p_confianza_reparacion: 2,
      p_servicio_taller: 3,
      p_calidad_mecanicos: 4,
      p_claridad_cobros: 5,
      p_originalidad_repuestos: null,
      observaciones: 'Todo bien',
      autoriza_datos: true,
    });
  });

  it('guards against double submit', async () => {
    let resolve;
    setupFetch({
      identificar: () => pendiente(),
      respuestas: () => new Promise((r) => { resolve = r; }),
    });
    render(<EncuestaPage />);
    await reachQ4();
    await user.click(screen.getByRole('radio', { name: 'No' }));
    await act(async () => {
      jest.advanceTimersByTime(250);
    });
    await user.click(screen.getByRole('radio', { name: 'No' }));
    await user.click(screen.getByRole('radio', { name: 'Sí' }));
    await act(async () => {
      jest.advanceTimersByTime(500);
    });
    expect(submitCalls()).toHaveLength(1);
    expect(JSON.parse(submitCalls()[0][1].body).autoriza_datos).toBe(false);
    await act(async () => {
      resolve({ ok: true, status: 200, json: async () => ({ clasificacion: 'SATISFECHO', caso_numero: null, primer_nombre: 'Juan' }) });
    });
  });

  async function submitWith(respuesta) {
    setupFetch({ identificar: () => pendiente(), respuestas: respuesta });
    render(<EncuestaPage />);
    await reachQ4();
    await user.click(screen.getByRole('radio', { name: 'Sí' }));
    await act(async () => {
      jest.advanceTimersByTime(250);
    });
  }

  it('detractor closing shows the case number', async () => {
    await submitWith(() => reply(200, { clasificacion: 'DETRACTOR', caso_numero: 42, primer_nombre: 'Juan' }));
    expect(await screen.findByText('Gracias por decírnoslo, Juan.')).toBeInTheDocument();
    expect(screen.getByText('Nuestro equipo de servicio al cliente te va a contactar.')).toBeInTheDocument();
    expect(screen.getByText('TU CASO')).toBeInTheDocument();
    expect(screen.getByText('No. 42')).toBeInTheDocument();
    expect(
      screen.getByText('Queda registrado a tu nombre. Si nadie te contacta, este número es tu respaldo.')
    ).toBeInTheDocument();
  });

  it('satisfied closing has no case box', async () => {
    await submitWith(() => reply(200, { clasificacion: 'SATISFECHO', caso_numero: null, primer_nombre: 'Juan' }));
    expect(await screen.findByText('Gracias, Juan.')).toBeInTheDocument();
    expect(screen.getByText('Tu opinión nos ayuda a mejorar.')).toBeInTheDocument();
    expect(screen.queryByText('TU CASO')).not.toBeInTheDocument();
  });

  it('409 shows the already answered screen', async () => {
    await submitWith(() => reply(409, { detail: 'YA_RESPONDIDA' }));
    expect(await screen.findByText('Ya recibimos tu calificación.')).toBeInTheDocument();
  });

  it('404 goes back to the cédula screen with a generic error', async () => {
    await submitWith(() => reply(404, { detail: 'REGISTRO_NO_ENCONTRADO' }));
    expect(await screen.findByLabelText('Ingresa tu número de cédula')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('No pudimos registrar tu respuesta');
  });

  it('a server error keeps the answers and offers a retry', async () => {
    await submitWith(() => reply(500, {}));
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos enviar tus respuestas');
    expect(screen.getByText(Q4)).toBeInTheDocument();
  });
});
