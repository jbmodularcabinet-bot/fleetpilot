/** Presentation only. The API recomputes all authoritative amounts. */
export function validDecimal(
  value: string,
  places: number,
  maximum: string,
  zero = false,
): boolean {
  if (!new RegExp(`^\\d{1,10}(\\.\\d{1,${places}})?$`).test(value))
    return false;
  const [whole, fraction = ""] = value.split(".");
  const scaled = BigInt(whole + fraction.padEnd(places, "0"));
  return (
    (zero ? scaled >= 0n : scaled > 0n) &&
    scaled <= BigInt(maximum) * 10n ** BigInt(places)
  );
}
export function php(value: string): string {
  if (!/^-?\d+(\.\d{1,2})?$/.test(value)) return "Unavailable";
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = (negative ? value.slice(1) : value).split(".");
  return `${negative ? "−" : ""}₱${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.padEnd(2, "0")}`;
}
export function fuelEstimate(liters: string, price: string): string | null {
  if (!/^\d+(\.\d{1,3})?$/.test(liters) || !/^\d+(\.\d{1,4})?$/.test(price))
    return null;
  const scale = (value: string, precision: number) => {
    const [whole, fraction = ""] = value.split(".");
    return BigInt(whole + fraction.padEnd(precision, "0"));
  };
  const cents = (scale(liters, 3) * scale(price, 4) + 50000n) / 100000n;
  return `${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
}
