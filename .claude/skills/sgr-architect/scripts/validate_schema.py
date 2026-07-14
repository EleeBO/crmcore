#!/usr/bin/env python3
"""
SGR Schema Validator

Проверяет Pydantic-схему на соответствие SGR best practices.
Использование: python validate_schema.py path/to/schema.py
"""

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class ValidationIssue:
    level: str  # "error" | "warning" | "info"
    message: str
    line: int | None = None


class SGRSchemaValidator:
    """Валидатор SGR-схем на основе статического анализа AST"""
    
    def __init__(self, source_code: str):
        self.source = source_code
        self.tree = ast.parse(source_code)
        self.issues: List[ValidationIssue] = []
        self.classes: dict[str, ast.ClassDef] = {}
        
        # Собираем все классы
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                self.classes[node.name] = node
    
    def validate(self) -> List[ValidationIssue]:
        """Запускает все проверки"""
        self.check_imports()
        self.check_base_classes()
        self.check_field_order()
        self.check_descriptions()
        self.check_na_handling()
        self.check_list_constraints()
        self.check_literal_usage()
        self.check_union_discriminator()
        
        return self.issues
    
    def check_imports(self):
        """Проверяет наличие необходимых импортов"""
        import_names = set()
        
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "pydantic":
                    import_names.update(alias.name for alias in node.names)
                elif node.module == "typing":
                    import_names.update(alias.name for alias in node.names)
        
        if "BaseModel" not in import_names:
            self.issues.append(ValidationIssue(
                "error",
                "Отсутствует импорт BaseModel из pydantic"
            ))
        
        if "Field" not in import_names:
            self.issues.append(ValidationIssue(
                "warning",
                "Рекомендуется импортировать Field из pydantic для описаний полей"
            ))
    
    def check_base_classes(self):
        """Проверяет, что классы наследуются от BaseModel"""
        for name, cls in self.classes.items():
            base_names = [
                base.id if isinstance(base, ast.Name) else 
                base.attr if isinstance(base, ast.Attribute) else None
                for base in cls.bases
            ]
            
            if "BaseModel" not in base_names and not any(
                base in self.classes for base in base_names
            ):
                self.issues.append(ValidationIssue(
                    "warning",
                    f"Класс {name} не наследуется от BaseModel",
                    line=cls.lineno
                ))
    
    def check_field_order(self):
        """Проверяет, что reasoning/analysis предшествует decision/conclusion"""
        reasoning_names = {"reasoning", "analysis", "thought", "observations", "assessment"}
        decision_names = {"decision", "conclusion", "result", "action", "verdict"}
        
        for name, cls in self.classes.items():
            field_names = []
            
            for item in cls.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_names.append(item.target.id.lower())
            
            # Находим позиции
            reasoning_pos = None
            decision_pos = None
            
            for i, field in enumerate(field_names):
                if any(r in field for r in reasoning_names):
                    reasoning_pos = i
                if any(d in field for d in decision_names):
                    decision_pos = i
            
            if reasoning_pos is not None and decision_pos is not None:
                if reasoning_pos > decision_pos:
                    self.issues.append(ValidationIssue(
                        "error",
                        f"В классе {name}: поле reasoning должно предшествовать decision (Cascade pattern)",
                        line=cls.lineno
                    ))
    
    def check_descriptions(self):
        """Проверяет наличие description у полей"""
        for name, cls in self.classes.items():
            for item in cls.body:
                if isinstance(item, ast.AnnAssign):
                    field_name = item.target.id if isinstance(item.target, ast.Name) else "unknown"
                    
                    # Проверяем, есть ли Field с description
                    has_description = False
                    
                    if item.value and isinstance(item.value, ast.Call):
                        for keyword in item.value.keywords:
                            if keyword.arg == "description":
                                has_description = True
                                
                                # Проверяем качество description
                                if isinstance(keyword.value, ast.Constant):
                                    desc = keyword.value.value
                                    if len(desc) < 10:
                                        self.issues.append(ValidationIssue(
                                            "warning",
                                            f"Поле {name}.{field_name}: description слишком короткий",
                                            line=item.lineno
                                        ))
                    
                    if not has_description and field_name not in ("kind",):
                        self.issues.append(ValidationIssue(
                            "warning",
                            f"Поле {name}.{field_name}: отсутствует description",
                            line=item.lineno
                        ))
    
    def check_na_handling(self):
        """Проверяет обработку N/A случаев"""
        has_na_handling = False
        has_optional = False
        
        for node in ast.walk(self.tree):
            # Проверяем Literal["N/A"]
            if isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Name) and node.value.id == "Literal":
                    if isinstance(node.slice, ast.Constant) and node.slice.value == "N/A":
                        has_na_handling = True
            
            # Проверяем Optional / | None
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                if isinstance(node.right, ast.Constant) and node.right.value is None:
                    has_optional = True
        
        if not has_na_handling and not has_optional:
            self.issues.append(ValidationIssue(
                "info",
                "Рекомендуется добавить обработку N/A случаев (Optional или Literal['N/A'])"
            ))
    
    def check_list_constraints(self):
        """Проверяет использование MinLen/MaxLen для списков"""
        for name, cls in self.classes.items():
            for item in cls.body:
                if isinstance(item, ast.AnnAssign):
                    annotation = item.annotation
                    
                    # Ищем List без Annotated
                    if isinstance(annotation, ast.Subscript):
                        if isinstance(annotation.value, ast.Name) and annotation.value.id == "List":
                            field_name = item.target.id if isinstance(item.target, ast.Name) else "unknown"
                            self.issues.append(ValidationIssue(
                                "warning",
                                f"Поле {name}.{field_name}: List без MinLen/MaxLen может привести к 'ленивой' генерации. "
                                "Рекомендуется: Annotated[List[T], MinLen(N), MaxLen(M)]",
                                line=item.lineno
                            ))
    
    def check_literal_usage(self):
        """Проверяет использование Literal для enum-значений"""
        # Это информационная проверка — ищем str поля без Literal
        for name, cls in self.classes.items():
            for item in cls.body:
                if isinstance(item, ast.AnnAssign):
                    annotation = item.annotation
                    field_name = item.target.id if isinstance(item.target, ast.Name) else "unknown"
                    
                    # Если тип просто str и имя похоже на enum
                    enum_like_names = {"status", "type", "kind", "category", "level", "severity", "priority"}
                    
                    if isinstance(annotation, ast.Name) and annotation.id == "str":
                        if any(e in field_name.lower() for e in enum_like_names):
                            self.issues.append(ValidationIssue(
                                "info",
                                f"Поле {name}.{field_name}: возможно, стоит использовать Literal вместо str",
                                line=item.lineno
                            ))
    
    def check_union_discriminator(self):
        """Проверяет наличие discriminator для Union типов"""
        for name, cls in self.classes.items():
            for item in cls.body:
                if isinstance(item, ast.AnnAssign):
                    annotation = item.annotation
                    
                    # Ищем Union
                    if isinstance(annotation, ast.Subscript):
                        if isinstance(annotation.value, ast.Name) and annotation.value.id == "Union":
                            # Проверяем, есть ли discriminator в Field
                            has_discriminator = False
                            
                            if item.value and isinstance(item.value, ast.Call):
                                for keyword in item.value.keywords:
                                    if keyword.arg == "discriminator":
                                        has_discriminator = True
                            
                            if not has_discriminator:
                                field_name = item.target.id if isinstance(item.target, ast.Name) else "unknown"
                                self.issues.append(ValidationIssue(
                                    "warning",
                                    f"Поле {name}.{field_name}: Union без discriminator. "
                                    "Рекомендуется добавить Field(discriminator='kind')",
                                    line=item.lineno
                                ))


def format_issues(issues: List[ValidationIssue]) -> str:
    """Форматирует результаты валидации"""
    if not issues:
        return "✅ Схема соответствует SGR best practices!"
    
    output = []
    
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    infos = [i for i in issues if i.level == "info"]
    
    if errors:
        output.append("❌ ОШИБКИ:")
        for issue in errors:
            line_info = f" (строка {issue.line})" if issue.line else ""
            output.append(f"  • {issue.message}{line_info}")
    
    if warnings:
        output.append("\n⚠️  ПРЕДУПРЕЖДЕНИЯ:")
        for issue in warnings:
            line_info = f" (строка {issue.line})" if issue.line else ""
            output.append(f"  • {issue.message}{line_info}")
    
    if infos:
        output.append("\nℹ️  РЕКОМЕНДАЦИИ:")
        for issue in infos:
            line_info = f" (строка {issue.line})" if issue.line else ""
            output.append(f"  • {issue.message}{line_info}")
    
    # Итог
    output.append(f"\n{'='*50}")
    output.append(f"Итого: {len(errors)} ошибок, {len(warnings)} предупреждений, {len(infos)} рекомендаций")
    
    if errors:
        output.append("❌ Схема требует исправлений")
    elif warnings:
        output.append("⚠️  Схема работоспособна, но рекомендуются улучшения")
    else:
        output.append("✅ Схема соответствует SGR best practices")
    
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Валидатор SGR-схем"
    )
    parser.add_argument(
        "schema_file",
        help="Путь к файлу со схемой (.py)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывод в JSON-формате"
    )
    
    args = parser.parse_args()
    
    schema_path = Path(args.schema_file)
    
    if not schema_path.exists():
        print(f"Ошибка: файл {schema_path} не найден")
        sys.exit(1)
    
    source_code = schema_path.read_text()
    
    try:
        validator = SGRSchemaValidator(source_code)
        issues = validator.validate()
        
        if args.json:
            import json
            result = [
                {"level": i.level, "message": i.message, "line": i.line}
                for i in issues
            ]
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(format_issues(issues))
        
        # Exit code: 1 если есть ошибки
        sys.exit(1 if any(i.level == "error" for i in issues) else 0)
        
    except SyntaxError as e:
        print(f"Ошибка синтаксиса Python: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
