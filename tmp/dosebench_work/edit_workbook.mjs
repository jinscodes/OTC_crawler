import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/jayhan/Downloads/DoseBench-V2_Dataset.xlsx";
const workDir = "/Users/jayhan/Desktop/Repo/OTC_crawler/tmp/dosebench_work";
const outputPath = "/Users/jayhan/Desktop/Repo/OTC_crawler/outputs/01a09bf9-098b-7cf3-ab1b-8dbea3cdd369/DoseBench-V2_Dataset_drug_focus_filled.xlsx";

const mapping = JSON.parse(
  await fs.readFile(`${workDir}/new_drug_focus_by_row.json`, "utf8"),
);
const expectedRows = Array.from({ length: 170 }, (_, index) => index + 2);
const actualRows = Object.keys(mapping).map(Number).sort((a, b) => a - b);

if (
  actualRows.length !== expectedRows.length ||
  actualRows.some((row, index) => row !== expectedRows[index])
) {
  throw new Error("drug_focus mapping must contain every worksheet row from 2 through 171 exactly once");
}

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Sheet4");

const labels = expectedRows.map((row) => [mapping[String(row)]]);
sheet.getRange("B2:B171").values = labels;
sheet.getRange("B1:B171").format.columnWidth = 24;

workbook.recalculate();

const keyCheck = await workbook.inspect({
  kind: "table",
  sheetId: "Sheet4",
  range: "A1:B171",
  include: "values,formulas",
  tableMaxRows: 171,
  tableMaxCols: 2,
  tableMaxCellChars: 220,
  maxChars: 60000,
});
await fs.writeFile(`${workDir}/final_table_check.ndjson`, keyCheck.ndjson);

const errorCheck = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
await fs.writeFile(`${workDir}/final_error_check.ndjson`, errorCheck.ndjson);

const preview = await workbook.render({
  sheetName: "Sheet4",
  range: "A1:B20",
  scale: 1,
  format: "png",
});
await fs.writeFile(
  `${workDir}/after_Sheet4.png`,
  new Uint8Array(await preview.arrayBuffer()),
);

await fs.mkdir(new URL(".", `file://${outputPath}`).pathname, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

console.log(JSON.stringify({ outputPath, populatedRows: labels.length }, null, 2));
