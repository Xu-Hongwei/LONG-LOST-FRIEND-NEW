import html2canvas from "html2canvas";
import type { LoveGender, LoveProfile } from "./data";

export async function saveLoveResultImageToPng(profile: LoveProfile, gender: LoveGender) {
  const modalElement = document.querySelector(".love-modal") as HTMLElement | null;
  if (!modalElement) return;

  const actionsBlock = document.querySelector(".modal-actions") as HTMLElement | null;
  const closeBtn = document.querySelector(".modal-close") as HTMLElement | null;
  if (actionsBlock) actionsBlock.style.display = "none";
  if (closeBtn) closeBtn.style.display = "none";

  const oldMaxHeight = modalElement.style.maxHeight;
  const oldOverflow = modalElement.style.overflow;
  modalElement.style.maxHeight = "none";
  modalElement.style.overflow = "visible";

  try {
    const canvas = await html2canvas(modalElement, {
      backgroundColor: "#121511",
      scale: 2,
      useCORS: true,
      logging: false
    });
    const anchor = document.createElement("a");
    anchor.href = canvas.toDataURL("image/png");
    anchor.download = `${profile.name}-${gender === "female" ? "女" : "男"}-恋爱人格结果.png`;
    anchor.click();
  } finally {
    modalElement.style.maxHeight = oldMaxHeight;
    modalElement.style.overflow = oldOverflow;
    if (actionsBlock) actionsBlock.style.display = "";
    if (closeBtn) closeBtn.style.display = "";
  }
}
