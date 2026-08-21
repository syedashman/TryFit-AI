import TryFitStudio from "@/components/tryfit/TryFitStudio";

export default function TryFitStudioPage({
  params,
  searchParams,
}: {
  params: { category: string; id: string };
  searchParams: { color?: string };
}) {
  return (
    <TryFitStudio
      category={params.category}
      productNumber={params.id}
      initialColor={searchParams.color}
    />
  );
}
