export class MoneyFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MoneyFormatError";
  }
}

const CURRENCY_FRACTION_DIGITS: Record<string, number> = {
  INR: 2,
};

export function getCurrencyFractionDigits(currency: string): number {
  const normalized = currency.trim().toUpperCase();
  if (normalized in CURRENCY_FRACTION_DIGITS) {
    return CURRENCY_FRACTION_DIGITS[normalized];
  }
  try {
    const digits = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: normalized,
    }).resolvedOptions().maximumFractionDigits;
    return digits ?? 2;
  } catch {
    throw new MoneyFormatError(`Unsupported currency: ${currency}`);
  }
}

export function parseMinorUnits(amountMinor: number | string): bigint {
  if (typeof amountMinor === "number") {
    if (!Number.isFinite(amountMinor) || !Number.isSafeInteger(amountMinor)) {
      throw new MoneyFormatError("Minor amount must be a safe integer.");
    }
    return BigInt(amountMinor);
  }

  const trimmed = amountMinor.trim();
  if (!/^-?\d+$/.test(trimmed)) {
    throw new MoneyFormatError("Minor amount must be an integer string.");
  }
  return BigInt(trimmed);
}

function formatMajorUnits(major: bigint, fractionDigits: number, negative: boolean): string {
  const scale = BigInt(10 ** fractionDigits);
  const absMajor = major < 0n ? -major : major;
  const whole = absMajor / scale;
  const fraction = absMajor % scale;
  const fractionText = fraction
    .toString()
    .padStart(fractionDigits, "0");
  const wholeText = whole.toString();
  const sign = negative ? "-" : "";
  if (fractionDigits === 0) {
    return `${sign}${wholeText}`;
  }
  return `${sign}${wholeText}.${fractionText}`;
}

export function formatMoney(amountMinor: number | string, currency: string): string {
  const normalizedCurrency = currency.trim().toUpperCase();
  const fractionDigits = getCurrencyFractionDigits(normalizedCurrency);
  const minor = parseMinorUnits(amountMinor);
  const negative = minor < 0n;
  const absMinor = negative ? -minor : minor;
  const majorText = formatMajorUnits(absMinor, fractionDigits, negative);

  if (normalizedCurrency === "INR") {
    const numeric = Number(majorText);
    if (Number.isFinite(numeric) && Math.abs(numeric) <= Number.MAX_SAFE_INTEGER) {
      return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        minimumFractionDigits: fractionDigits,
        maximumFractionDigits: fractionDigits,
      }).format(numeric);
    }
    return `INR ${majorText}`;
  }

  const numeric = Number(majorText);
  if (Number.isFinite(numeric) && Math.abs(numeric) <= Number.MAX_SAFE_INTEGER) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: normalizedCurrency,
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    }).format(numeric);
  }

  return `${normalizedCurrency} ${majorText}`;
}
