import ProductDetail from "@/components/ProductDetail";

export default function ProductPage({
  params,
}: {
  params: { category: string; id: string };
}) {
  return (
    <ProductDetail category={params.category} productNumber={params.id} />
  );
}
