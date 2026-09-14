import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/jayhan/Downloads/DoseBench-V2_Dataset.xlsx";
const workDir = "/Users/jayhan/Desktop/Repo/OTC_crawler/tmp/dosebench_work";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook,sheet,table,drawing,definedName",
  maxChars: 12000,
  tableMaxRows: 8,
  tableMaxCols: 12,
  tableMaxCellChars: 160,
});
console.log(summary.ndjson);

const sheetInfo = [];
for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange();
  sheetInfo.push({
    name: sheet.name,
    usedAddress: used?.address ?? null,
    rowCount: used?.rowCount ?? null,
    columnCount: used?.columnCount ?? null,
  });
  await fs.writeFile(
    `${workDir}/sheet_${sheet.name}_values.json`,
    JSON.stringify(used.values, null, 2),
  );
  try {
    const preview = await workbook.render({
      sheetName: sheet.name,
      range: "A1:B15",
      scale: 1,
      format: "png",
    });
    const safeName = sheet.name.replace(/[^A-Za-z0-9_-]+/g, "_");
    await fs.writeFile(
      `${workDir}/before_${safeName}.png`,
      new Uint8Array(await preview.arrayBuffer()),
    );
  } catch (error) {
    console.error(`RENDER_ERROR: ${error?.message ?? String(error)}`);
  }
}

await fs.writeFile(`${workDir}/sheet_info.json`, JSON.stringify(sheetInfo, null, 2));
console.log(JSON.stringify(sheetInfo, null, 2));
