import subprocess
import shlex
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

class PowerShellAgent:
    def __init__(self, model_name: str = 'gpt2', device: str = 'cpu'):
        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(model_name).to(device)
        self.device = device

    def generate_powershell(self, user_request: str, max_length: int = 200) -> str:
        """
        Generate a PowerShell script snippet based on the user request using model.generate(),
        avoiding the pipeline to prevent extra sklearn/numpy imports.
        """
        prompt = (
            "# Convert the following user request into a PowerShell script\n"
            f"# User request: {user_request}\n"
            "# PowerShell script:\n"
        )
        inputs = self.tokenizer(prompt, return_tensors='pt').to(self.device)
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=max_length,
            do_sample=True,
            top_p=0.95,
            temperature=0.7,
            pad_token_id=self.tokenizer.eos_token_id
        )
        generated = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Extract only the script portion
        return generated[len(prompt):].strip()

    def confirm_execution(self, script: str) -> bool:
        print("\nGenerated PowerShell script:")
        print("---------------------------------")
        print(script)
        print("---------------------------------\n")
        choice = input("Do you want to execute this script? (yes/no): ").strip().lower()
        return choice in ['yes', 'y']

    def execute_script(self, script: str) -> subprocess.CompletedProcess:
        temp_file = 'temp_script.ps1'
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(script)
        command = f"powershell -ExecutionPolicy Bypass -File {temp_file}"
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True
        )
        return result

    def handle_request(self, user_request: str):
        try:
            script = self.generate_powershell(user_request)
        except ImportError as e:
            print("Error generating script: numpy/transformers version mismatch detected.")
            print("Please install a compatible numpy (<2.0) or rebuild affected modules.")
            return

        if not self.confirm_execution(script):
            print("Execution canceled by user.")
            return

        result = self.execute_script(script)
        print(f"\nReturn code: {result.returncode}")
        print("\nStandard Output:\n", result.stdout)
        print("\nStandard Error:\n", result.stderr)


def main():
    print("=== LLM-Powered PowerShell Agent ===")
    model_name = input("Enter model name (default 'gpt2'): ").strip() or 'gpt2'
    device = input("Enter device ('cpu' or GPU index, e.g. 'cuda:0'): ").strip() or 'cpu'
    user_request = input("\nDescribe the Windows task to automate: ").strip()

    agent = PowerShellAgent(model_name=model_name, device=device)
    agent.handle_request(user_request)

if __name__ == "__main__":
    main()
