export function captureRunConditions() {
  const load = window.prompt('Record the load ID for this run, such as no-load or fixture-A-85g.')
  if (!load?.trim()) return null
  const condition = window.prompt('Record the physical test condition, including any applied friction.')
  if (!condition?.trim()) return null
  const mass = window.prompt('Attached mass in grams. Leave blank if no mass measurement is documented.', '')
  if (mass === null) return null
  const grams = mass.trim() === '' ? null : Number(mass)
  if (grams !== null && (!Number.isFinite(grams) || grams < 0)) {
    window.alert('Enter a finite, nonnegative mass in grams.')
    return null
  }
  return { load_id: load.trim(), condition: condition.trim(), attached_mass_g: grams }
}
