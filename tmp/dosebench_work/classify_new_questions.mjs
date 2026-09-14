import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workDir = "/Users/jayhan/Desktop/Repo/OTC_crawler/tmp/dosebench_work";
const previousOutputPath = "/Users/jayhan/Desktop/Repo/OTC_crawler/outputs/dosebench_drug_focus/DoseBench-V2_Dataset_drug_focus_filled.xlsx";
const rows = JSON.parse(
  await fs.readFile(`${workDir}/sheet_Sheet4_values.json`, "utf8"),
);

const previousWorkbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load(previousOutputPath),
);
const previousRows = previousWorkbook.worksheets
  .getItem("Sheet4")
  .getRange("A2:B171").values;
const previousLabelsByQuestion = new Map(
  previousRows
    .filter((row) => row[0] && row[1])
    .map((row) => [String(row[0]).trim(), String(row[1]).trim()]),
);

const tylenolPattern = /\b(?:tylenol|acetaminophen|acetominophen|acetaminaphen|paracetamol|apap|panadol)\b/i;
const advilPattern = /\b(?:advil|ibuprofen(?:s)?|ibuprophen|ibufrofen|ibufrofin|motrin|nurofen|brufen)\b/i;

const mapping = {};
const review = [];
for (let index = 1; index < rows.length; index += 1) {
  const text = String(rows[index]?.[0] ?? "").trim();
  if (!text) continue;
  const priorLabel = previousLabelsByQuestion.get(text);
  const hasTylenol = tylenolPattern.test(text);
  const hasAdvil = advilPattern.test(text);
  let label = priorLabel;
  let source = "previous_review";
  if (!label) {
    source = "keyword_classification";
    if (hasTylenol && hasAdvil) label = "Tylenol_Advil";
    else if (hasTylenol) label = "Tylenol";
    else if (hasAdvil) label = "Advil";
    else label = "REVIEW";
  }
  const sheetRow = index + 1;
  mapping[sheetRow] = label;
  review.push({ sheetRow, label, source, text });
}

await fs.writeFile(
  `${workDir}/new_drug_focus_by_row.json`,
  JSON.stringify(mapping, null, 2),
);
await fs.writeFile(
  `${workDir}/new_classification_review.json`,
  JSON.stringify(review, null, 2),
);

const counts = review.reduce((acc, item) => {
  acc[item.label] = (acc[item.label] ?? 0) + 1;
  return acc;
}, {});
const sources = review.reduce((acc, item) => {
  acc[item.source] = (acc[item.source] ?? 0) + 1;
  return acc;
}, {});
console.log(JSON.stringify({ rows: review.length, counts, sources }, null, 2));
for (const item of review.filter(({ label }) => label === "REVIEW")) {
  console.log(`UNMATCHED ROW ${item.sheetRow}: ${item.text}`);
}
