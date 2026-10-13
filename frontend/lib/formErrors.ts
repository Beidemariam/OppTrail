/**
 * What the browser refused, keyed the way the API keys its own refusals.
 *
 * Milestone 6.5a, and the second half of a defect the human found twice. The
 * first half was D-180: a 422's reasons were never read, so a refused form
 * said only "The request could not be validated". This is the other path to
 * the same silence — **the browser's own constraint validation**, which stops
 * a submit before any of our code runs:
 *
 * > *"Doesn't take in words for number of days, except for some reason the
 * > letter e, and it doesn't say what to fix."*
 *
 * Both halves of that are real. A `<input type="number">` keeps `e` on screen
 * (it is legal in `1e5`) while reporting its value as the empty string with
 * `validity.badInput` set — so the field looks filled and reads as empty. And
 * because the field is `required`, the browser cancels the submit, shows a
 * tooltip that vanishes, and leaves the form exactly as it was. Nothing in
 * the app had a chance to say anything.
 *
 * The fix is to take validation off the browser's hands and ask it the same
 * questions ourselves: `noValidate` on the form, then `invalidFields` on
 * submit, whose answers go through the same per-field display a 422's do. The
 * messages are still the browser's own — "Please enter a number." is better
 * than anything invented here, and it is already localized.
 *
 * The keys come from each control's `name`, which is deliberately the API's
 * field path (`"action.title"`): one vocabulary for both kinds of refusal, so
 * the form needs no translation table between them.
 */
export function invalidFields(form: HTMLFormElement): Record<string, string> {
  const reasons: Record<string, string> = {};
  for (const element of Array.from(form.elements)) {
    const control = element as HTMLInputElement;
    if (typeof control.checkValidity !== "function" || control.disabled) {
      continue;
    }
    if (!control.checkValidity() && control.name) {
      reasons[control.name] = control.validationMessage;
    }
  }
  return reasons;
}
