/** Static presentation content for Phase 2 UI preview only. */
export const CODE_FLOW_EXAMPLE = {
  label: "Example code flow",
  description: "A static preview of the kind of trace OverHaust will surface.",
  steps: [
    "OrderService.addOrder",
    "_enqueueKitchenPrintForLatestOrder",
    "enqueueRoutedJobsForOrder",
    "buildKotText",
    "KitchenPrintDocumentBuilder",
  ],
} as const;
