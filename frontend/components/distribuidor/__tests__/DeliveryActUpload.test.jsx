/**
 * Tests for the delivery-act file picker (Distribuidor screen).
 *
 * A Distribuidor's delivery act is a different document than a workshop's
 * damage-reception photos -- it's commonly scanned/signed as PDF, so the
 * picker must accept PDF alongside images (user decision, 2026-07-29,
 * corrects the PR7 default which only allowed images).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import DeliveryActUpload from '../DeliveryActUpload';

test('the file input accepts both images and PDF', () => {
  render(<DeliveryActUpload value={null} onChange={() => {}} />);
  const input = screen.getByLabelText(/foto del acta de entrega/i);
  expect(input).toHaveAttribute('accept', 'image/*,application/pdf');
});
