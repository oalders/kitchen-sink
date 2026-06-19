# Perl Review Standards

A living checklist applied by the `perl-review` skill. Edit it freely — the
review reads whatever is here at runtime.

## How to extend

Append a row to the appropriate table below. No other file needs touching.

- **Scope** is the table the row lives in: **General** (all Perl) or **Tests**
  (`.t` files).
- **Type** — `clear` (report as a violation) or `judgment` (report as a
  suggestion; the author may have a deliberate reason).

## General

| Rule | Detail | Type |
|------|--------|------|
| prefer core modules | Avoid custom code when a core Perl module does the same thing. | judgment |
| no compile-only tests | If a module has unit tests, delete any test whose only job is checking the module compiles. | clear |
| prefer `use` over `require` | Use `require` sparingly; prefer `use`. | judgment |
| single-quote non-interpolated strings | Prefer single quotes where no interpolation is required. Don't flag literals containing apostrophes or an intentional literal `$`/`@`, where switching quotes would need escaping. | clear |
| alpha-sort hash keys | Hash keys should be alpha-sorted. Keys are often ordered intentionally (grouping, precedence), so suggest rather than assert. | judgment |
| build URLs with URI | Use the `URI` module to build URLs rather than string concatenation. | judgment |
| don't quote bareword hash keys | Don't quote hash keys that don't require it. | clear |
| prefer Try::Tiny over eval | Prefer `Try::Tiny` over `eval` for exception handling. Modern Perl also has native `try/catch`, and not every `eval` is exception handling (e.g. `eval { require Foo }`), so suggest rather than assert. | judgment |

## Tests

| Rule | Detail | Type |
|------|--------|------|
| no Pod in tests | Test files don't need Pod. | clear |
| comments into test descriptions | Tests probably don't need comments; put the comment into the test description instead. | judgment |
| group with subtests | If you want to describe a set of tests, consider a subtest. | judgment |
| table-driven tests | Consider table-driven tests or subtests to avoid shadowing vars. | judgment |
| no use_ok | Don't use `use_ok()` to assert a module can be loaded / is present. | clear |
| no isa_ok on new() | Don't use `isa_ok()` to assert what `new()` returns. | clear |
| Test::Fatal for exceptions | Prefer `Test::Fatal` for testing exceptions. | clear |
