import type { InvoiceFields } from "@/lib/api";
import { formatMoney } from "@/lib/format";

export default function LineItemsTable({
  fields,
  currency,
}: {
  fields: InvoiceFields;
  currency: string | null;
}) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-200 px-5 py-3">
        <h2 className="text-base font-semibold text-gray-900">Line items</h2>
        <p className="mt-1 text-xs text-gray-500">Read-only. Amounts are shown as printed.</p>
      </div>
      {fields.line_items.length === 0 ? (
        <p className="px-5 py-4 text-sm text-gray-600">No line items were read.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-5 py-2 font-medium">Description</th>
                <th className="px-5 py-2 text-right font-medium">Qty</th>
                <th className="px-5 py-2 text-right font-medium">Unit price</th>
                <th className="px-5 py-2 text-right font-medium">Amount</th>
                <th className="px-5 py-2 font-medium">Page</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {fields.line_items.map((item, i) => (
                <tr key={i} title={item.evidence.line}>
                  <td className="px-5 py-2 text-gray-900">{item.description}</td>
                  <td className="px-5 py-2 text-right tabular-nums">{item.quantity}</td>
                  <td className="px-5 py-2 text-right tabular-nums">
                    {formatMoney(item.unit_price, currency)}
                  </td>
                  <td className="px-5 py-2 text-right tabular-nums">
                    {formatMoney(item.amount, currency)}
                  </td>
                  <td className="px-5 py-2 text-gray-500">{item.evidence.page_number}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {fields.extraction_notes.length > 0 && (
        <ul className="border-t border-gray-100 px-5 py-3 text-xs text-amber-800">
          {fields.extraction_notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
