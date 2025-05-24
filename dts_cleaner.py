import os
import re
import sys

PHANDLE_VARS_OUTPUT="phandles.txt"
PHANDLE_PATTERN = re.compile(r'^( |\t)*phandle = <(.+?)>;$', re.MULTILINE)
VAR_SET_PATTERN = re.compile(r'^( |\t)*([^\n]*?)( |\t)=( |\t)?[^;]*?(<.*?>);',
                             re.MULTILINE | re.DOTALL)
SUBVALUES_PATTERN = re.compile(r'<(.+?)>')

def main():
    if len(sys.argv) != 2:
        print("Usage: dts_cleaner.py <dts>")
        print("This script will automatically detect if the DTS " +
              "is from a kernel's source code or from a DTB.")
        print("In the first case, it'll write to 'phandles.txt' which values are phandles. ")
        print("In the second case, it'll output a copy of the DTS with " +
              "the phandles replaced with their respective labels.")
        sys.exit(1)

    dts_path = sys.argv[1]
    if not os.path.isfile(dts_path):
        print(f"File not found: '{dts_path}'")
        sys.exit(2)

    with open(dts_path, 'r') as dts:
        content = dts.read()

        if re.search(PHANDLE_PATTERN, content) is None:
            print("DTS from kernel source detected, exporting phandle variables...")
            export_phandle_vars(content)
        else:
            out_file = f"{dts_path}_cleaned"
            print(f"DTS from DTB detected, replacing phandles " +
                  f"and saving to '{out_file}'...")
            replace_phandles(content, out_file)
    
    print("Done!")

def export_phandle_vars(content: str):
    phandle_vars = set()

    for match in re.findall(VAR_SET_PATTERN, content):
        var_name = match[1]
        value = match[4]

        if not '&' in value:
            continue

        i = 0
        for subvalues in re.findall(SUBVALUES_PATTERN, value):
            for subvalue in subvalues.split(' '):
                subvalue = subvalue.strip()
                if subvalue.startswith('&'):
                    phandle_vars.add(f'{var_name};{i}')
                
                i += 1

    if not os.path.isfile(PHANDLE_VARS_OUTPUT):
        open(PHANDLE_VARS_OUTPUT, 'w').close()

    with open(PHANDLE_VARS_OUTPUT, 'r+') as out:
        stored_vars = out.readlines()

        added_amount = len(phandle_vars)
        for var in stored_vars:
            var_name = var.removesuffix('\n')
            if not var_name in phandle_vars:
                phandle_vars.add(var_name)
            else:
                added_amount -= 1
        
        # We also want 'phandle = <X>;' replaced
        if not "phandle;0" in phandle_vars:
            phandle_vars.add("phandle;0")
            added_amount += 1

        out.seek(0)
        out.writelines(f'{v}\n' for v in phandle_vars)
        print(f"Added {added_amount} phandle variable names to " +
              f"{PHANDLE_VARS_OUTPUT}, adding a total of {len(phandle_vars)}")

def read_symbols(content: str) -> dict[str, str]:
    symbols_pattern = re.compile(r'( |\t)*__symbols__ {\n(.+?)};', re.DOTALL)
    m = re.search(symbols_pattern, content)
    if m is None:
        print("Error: Couldn't find symbols")
        sys.exit(4)
    
    symbols = m.group(2).splitlines()
    symbols_dict = {}
    for sym in symbols:
        sym = sym.strip()
        if len(sym) == 0:
            continue

        m = re.match(r'^(.+?) = "(.+?)";$', sym)
        if m is None:
            print(f"Warning: Couldn't parse symbol '{repr(sym)}'")
            continue
        
        symbols_dict[m.group(2)] = m.group(1)

    print(f"Registered {len(symbols_dict)} symbols")
    return symbols_dict

def read_phandle_paths(content: str) -> dict[str, str]:
    current_path = ""
    paths = {}

    for line in content.splitlines():
        line = line.strip()
        if line.endswith('{'):
            # print(f"open {line}")
            current_path += f"{line.strip(' {')}"
            if not current_path.endswith('/'):
                current_path += "/"
            # print(current_path)
            continue
        elif line.endswith('};'):
            # print(line)
            current_path = current_path.removesuffix('/')
            if len(current_path) > 0:
                current_path = current_path[:current_path.rindex('/') + 1]
            if len(current_path) == 0:
                current_path = "/"
            continue

        m = re.match(PHANDLE_PATTERN, line)
        if m is None:
            continue
            
        paths[m.group(2)] = current_path
    
    print(f"Registered the path of {len(paths)} phandles")
    return paths

def replace_phandles(content: str, out_file: str):
    if not os.path.isfile(PHANDLE_VARS_OUTPUT):
        print(f"Couldn't find '{PHANDLE_VARS_OUTPUT}'")
        print("Tip: You need to first run this script passing it " +
              "one or more DTS files from the kernel source code")
        sys.exit(3)
    
    symbols = read_symbols(content)
    paths = read_phandle_paths(content)
    if len(symbols) != len(paths):
        print(f"Warning: Amount of symbols doesn't match amount of " +
               "phandle paths, something may have gone wrong")

    lines = content.splitlines()
    with open(PHANDLE_VARS_OUTPUT, 'r') as f:
        phandle_vars: dict[str, set[int]] = {}
        for entry in f.readlines():
            splitted = entry.split(';')
            if len(splitted) != 2:
                continue

            var = splitted[0]
            index = splitted[1].strip()
            index = int(index)
            
            phandle_vars.setdefault(var, set()).add(index)

        print("Replacing phandles... please wait")
        replaced=0
        for line_i, line in enumerate(lines):
            m = re.match(VAR_SET_PATTERN, line)
            if m is None:
                continue

            var_name = m.group(2)
            value = m.group(5)
            if not var_name in phandle_vars.keys():
                continue
            
            value = value.removeprefix('<').removesuffix('>')
            new_value = ''
            for i, subvalue in enumerate(value.split(' ')):
                if not i in phandle_vars[var_name]:
                    new_value += f' {subvalue}'
                    continue

                phandle = subvalue.strip()
                if not phandle in paths.keys():
                    print(f'{var_name} ; {i}')
                    print(f"Warning: Couldn't find path of phandle '{phandle}'")
                    continue

                sym = symbols[paths[phandle].removesuffix('/')]
                new_value += f' &{sym}'
                replaced += 1

            lines[line_i] = lines[line_i].replace(value, new_value.strip())
        
        print(f'{replaced} phandle references replaced with their symbol')
        with open(out_file, 'w') as out:
            out.writelines(f'{l}\n' for l in lines)

if __name__ == "__main__":
    main()