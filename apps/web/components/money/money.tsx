import { formatMoney } from "@/lib/money/format-money";

interface MoneyProps {
  amountMinor: number | string;
  currency: string;
  className?: string;
}

export function Money({ amountMinor, currency, className }: MoneyProps) {
  const formatted = formatMoney(amountMinor, currency);
  return (
    <span className={className} aria-label={`${formatted} ${currency}`}>
      {formatted}
    </span>
  );
}
