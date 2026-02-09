// Simple test file for demo

const { main } = require('./index');

console.log('Running tests...');

// Test 1: main function exists
if (typeof main !== 'function') {
  console.error('FAIL: main is not a function');
  process.exit(1);
}

// Test 2: main function runs without error
try {
  main();
  console.log('PASS: main function executed successfully');
} catch (error) {
  console.error('FAIL: main function threw an error:', error);
  process.exit(1);
}

console.log('All tests passed!');
