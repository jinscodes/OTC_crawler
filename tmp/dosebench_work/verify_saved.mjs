import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const sourcePath = "/Users/jayhan/Downloads/DoseBench-V2_Dataset.xlsx";
const outputPath = "/Users/jayhan/Desktop/Repo/OTC_crawler/outputs/01a09bf9-098b-7cf3-ab1b-8dbea3cdd369/DoseBench-V2_Dataset_drug_focus_filled.xlsx";
const workDir = "/Users/jayhan/Desktop/Repo/OTC_crawler/tmp/dosebench_work";

const [source, output] = await Promise.all([
  SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath)),
  SpreadsheetFile.importXlsx(await FileBlob.load(outputPath)),
]);

const sourceSheet = source.worksheets.getItem("Sheet4");
const outputSheet = output.worksheets.getItem("Sheet4");
const sourceQuestions = sourceSheet.getRange("A1:A171").values;
const outputQuestions = outputSheet.getRange("A1:A171").values;
if (JSON.stringify(sourceQuestions) !== JSON.stringify(outputQuestions)) {
  throw new Error("Question text changed during the edit");
}

const labels = outputSheet.getRange("B2:B171").values.map((row) => row[0]);
if (labels.length !== 170 || labels.some((value) => !value)) {
  throw new Error("Expected 170 populated drug_focus cells");
}

const counts = {};
for (const label of labels) counts[label] = (counts[label] ?? 0) + 1;

const sourceTableMetadata = sourceSheet.tables.items.map((table) => ({
  name: table.name,
  style: table.style,
  showHeaders: table.showHeaders,
  showTotals: table.showTotals,
  showBandedColumns: table.showBandedColumns,
  showFilterButton: table.showFilterButton,
}));

const errorCheck = await output.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "saved workbook formula error scan",
});

const spotCheck = await output.inspect({
  kind: "table",
  sheetId: "Sheet4",
  range: "A84:B118",
  include: "values,formulas",
  tableMaxRows: 35,
  tableMaxCols: 2,
  tableMaxCellChars: 180,
  maxChars: 20000,
});
await fs.writeFile(`${workDir}/saved_spot_check.ndjson`, spotCheck.ndjson);

const preview = await output.render({
  sheetName: "Sheet4",
  range: "A1:B20",
  scale: 1,
  format: "png",
});
await fs.writeFile(
  `${workDir}/reopened_Sheet4.png`,
  new Uint8Array(await preview.arrayBuffer()),
);

console.log(JSON.stringify({
  sheets: output.worksheets.items.map((sheet) => sheet.name),
  tables: outputSheet.tables.items.length,
  sourceTableMetadata,
  populated: labels.length,
  blank: labels.filter((value) => !value).length,
  counts,
  formulaErrorScan: errorCheck.ndjson || "no matches",
}, null, 2));
