# PHP standards

Drop-in for PHP work. Extends `../coding-standards.md`; the universal floor (OWASP, SOLID, TDD, the privacy floor) still applies in full. This file only adds what is specific to PHP.

## PSR is the baseline

- **PSR-12** for code style. I don't hand-format or invent a house style; the ecosystem already agreed on one. Where a formatter is available (PHP-CS-Fixer, Pint on Laravel), it owns the formatting and I don't argue with it by hand.
- **PSR-4** for autoloading. Namespace maps to directory, one class per file, class name matches file name. No manual `require` chains for application code.
- **PSR-7 / PSR-15** when I build or touch the HTTP layer directly: request/response as PSR-7 messages, middleware as PSR-15 handlers. This keeps HTTP code portable across frameworks instead of bound to one framework's request object. I don't reach for these inside a framework that already gives me its own request abstraction unless I'm working at the layer where they buy something.
- **PSR-3** for logging interfaces, **PSR-11** for container access, when the code is a library meant to run outside one app.

## Framework conventions win over cleverness

- On Laravel, I follow Laravel's own conventions rather than fighting the framework: Eloquent where it fits, form requests for validation, the container for wiring, migrations for schema. A pattern the framework already provides is not something I reimplement (this is the reuse rung of the ladder, applied to the framework).
- Types on everything the language lets me type: parameters, return types, properties. `declare(strict_types=1)` at the top of files I own. A green static analysis pass (PHPStan/Psalm) is a shape check, not a correctness verdict, same rule as the universal floor.
- Parameterized queries only, through the query builder or prepared statements. This restates the floor because raw SQL is where PHP code most often violates it.
