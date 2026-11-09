import {readFile,mkdir,writeFile,copyFile} from 'node:fs/promises';
const contract=await readFile('worker/contract.mjs','utf8');
const source=(await readFile('worker/index.js','utf8')).replace("import { ANSWER_SCHEMA, PROMPT } from './contract.mjs';",'');
await mkdir('dist/server',{recursive:true});await mkdir('dist/.openai',{recursive:true});
await writeFile('dist/server/index.js',contract.replaceAll('export const ','const ')+'\n'+source);
await copyFile('.openai/hosting.json','dist/.openai/hosting.json');
console.log('Built self-contained cloud Worker.');
