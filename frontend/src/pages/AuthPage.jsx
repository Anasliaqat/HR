import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../services/api";

export default function AuthPage() {
  const [role,setRole]=useState("candidate");
  const [mode,setMode]=useState("login");
  const [name,setName]=useState("");
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [code,setCode]=useState("");
  const [pending,setPending]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const navigate=useNavigate();
  async function submit(event){
    event.preventDefault();setError("");setMessage("");setPending(true);
    try{
      let data;
      if(mode==="verify"){data=await api.verifyHr({email,code});}
      else if(mode==="signup"){
        if(role==="hr"){await api.registerHr({full_name:name,email,password});setMode("verify");setMessage("Verification code sent to the authorized HR inbox.");return;}
        data=await api.registerCandidate({full_name:name,email,password});
      } else data=await api.login({email,password});
      if(data.access_token){localStorage.setItem("hireflow.accessToken",data.access_token);localStorage.setItem("hireflow.role",data.role);localStorage.setItem("hireflow.email",data.email);navigate(data.role==="hr"?"/dashboard":"/candidate");}
    }catch(e){setError(e.message);}finally{setPending(false);}
  }
  return <main style={{maxWidth:460,margin:"8vh auto",padding:28,border:"1px solid var(--border)",borderRadius:18,background:"var(--surface)"}}>
    <p className="eyebrow">ZETECH · HIRING PORTAL</p><h1>{mode==="verify"?"Verify HR email":mode==="signup"?"Create account":"Welcome back"}</h1>
    {mode!=="verify"&&<><div style={{display:"flex",gap:8,marginBottom:18}}><button type="button" onClick={()=>{setRole("candidate");setMode("login")}}>Candidate</button><button type="button" onClick={()=>{setRole("hr");setMode("login")}}>HR</button></div><p>{role==="hr"?"Authorized HR access":"Candidate job application portal"}</p><div style={{display:"flex",gap:8,marginBottom:16}}><button type="button" onClick={()=>setMode("login")}>Login</button><button type="button" onClick={()=>setMode("signup")}>Sign up</button></div></>}
    <form onSubmit={submit} style={{display:"grid",gap:12}}>
      {(mode==="signup")&&<input required placeholder="Full name" value={name} onChange={e=>setName(e.target.value)}/>}
      <input required type="email" placeholder="Email address" value={email} onChange={e=>setEmail(e.target.value)}/>
      {mode!=="verify"&&<input required minLength={12} type="password" placeholder="Password (at least 12 characters)" value={password} onChange={e=>setPassword(e.target.value)}/>}
      {mode==="verify"&&<input required minLength={6} maxLength={6} placeholder="6-digit verification code" value={code} onChange={e=>setCode(e.target.value)}/>}
      <button className="button button-primary" disabled={pending}>{pending?"Please wait":mode==="verify"?"Verify email":mode==="signup"?"Create account":"Login"}</button>
    </form>
    {message&&<p role="status">{message}</p>}{error&&<p role="alert" style={{color:"crimson"}}>{error}</p>}
    <p style={{marginTop:18}}><Link to="/">Back to portal</Link></p>
  </main>;
}
