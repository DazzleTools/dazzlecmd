// Echoes all argv entries after node + script to verify argv propagation.
const args = process.argv.slice(2);
console.log(`ARGS: ${JSON.stringify(args)}`);
