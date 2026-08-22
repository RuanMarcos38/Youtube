import AutoEditLauncher from "@/components/AutoEditLauncher";
import DiagnosticsAssistant from "@/components/DiagnosticsAssistant";
import SaasApp from "@/components/SaasApp";

export default function Home() {
  return (
    <>
      <SaasApp />
      <DiagnosticsAssistant />
      <AutoEditLauncher />
    </>
  );
}
