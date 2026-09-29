import { useRef } from 'react';

/**
 * Accessible radiogroup with roving tabindex and arrow-key navigation.
 * options: [{ value, label, className? }]; value: the selected option value.
 */
export default function ChoiceGroup({ label, options, value, onChange, className, disabled = false }) {
  const ref = useRef(null);
  const selectedIndex = options.findIndex((o) => o.value === value);

  const move = (event, index) => {
    const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    if (!(event.key in keys)) return;
    event.preventDefault();
    const next = (index + keys[event.key] + options.length) % options.length;
    onChange(options[next].value);
    ref.current.querySelectorAll('[role="radio"]')[next].focus();
  };

  return (
    <div role="radiogroup" aria-label={label} className={className} ref={ref}>
      {options.map((option, index) => (
        <button
          key={String(option.value)}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          tabIndex={index === (selectedIndex === -1 ? 0 : selectedIndex) ? 0 : -1}
          disabled={disabled}
          className={`enc-choice ${option.className || ''}`}
          onClick={() => onChange(option.value)}
          onKeyDown={(event) => move(event, index)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
