// Sélection multiple sous forme de pastilles cliquables (bandes, opérateurs).
interface Props {
  label: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
}

export default function ChipSelect({ label, options, selected, onChange }: Props) {
  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);

  return (
    <fieldset className="field">
      <legend>
        {label} <span className="muted small">({selected.length})</span>
      </legend>
      <div className="chips">
        {options.map((option) => {
          const on = selected.includes(option);
          return (
            <button
              type="button"
              key={option}
              className={on ? "chip on" : "chip"}
              aria-pressed={on}
              onClick={() => toggle(option)}
            >
              {option}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}