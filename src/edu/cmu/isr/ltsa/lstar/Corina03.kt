package edu.cmu.isr.ltsa.lstar

import edu.cmu.isr.ltsa.LTSACall

fun main() {
//  val M1 = "Input = (input -> send -> ack -> Input)."
//  val M2 = "Output = (send -> output -> ack -> Output)."
//  val P = "property Order = (input -> output -> Order)."

//  val M1 = "Input = (input -> send -> ack -> Input)."
//  val M2 = "Output = (send -> SEND), SEND = (send -> SEND | output -> ack -> Output)."
//  val P = "property Order = (input -> output -> Order)."

//  val M1 = "P_SENDER = (input -> e.send_s -> e.ack_s -> P_SENDER).\n" +
//      "RECEIVER = (e.send_r -> output -> e.ack_r -> RECEIVER).\n" +
//      "||SYS = (P_SENDER || RECEIVER)."
//  val M2 = "P_CHANNEL = (e.send_s -> e.send_r -> e.ack_r -> e.ack_s -> P_CHANNEL)."
//  val P = "property P = (input -> output -> P)."

  val M1 = "L1_SENDER = (input -> e.send_s -> (e.send_s -> e.ack_s -> L1_SENDER | e.ack_s -> L1_SENDER)).\n" +
      "RECEIVER = (e.send_r -> output -> e.ack_r -> RECEIVER).\n" +
      "||SYS = (L1_SENDER || RECEIVER)."
  val M2 = "LOSS_1_CHANNEL = (e.send_s ->\n" +
      "    (e.send_r -> e.ack_r -> e.ack_s -> LOSS_1_CHANNEL\n" +
      "   | e.drop -> e.send_s -> e.send_r -> e.ack_r -> e.ack_s -> LOSS_1_CHANNEL)\n" +
      ")."
  val P = "property P = (input -> output -> P)."

  val lStar = CorinaLStar(M1, M2, P)
  lStar.run()
}

private class CorinaLStar(val M1: String, val M2: String, val P: String) {
  private val Σ: Set<String>
  private val S = mutableSetOf<String>("")
  private val E = mutableSetOf<String>("")
  private val T = mutableMapOf<String, Boolean>("" to true)
  private val nameM1: String
  private val nameM2: String
  private val nameP: String

  init {
    println("========== Parsing the alphabets ==========")
    val ltsaCall = LTSACall()
    var sm = ltsaCall.doCompile(M1)
    val αM1 = ltsaCall.getAllAlphabet(sm)
    nameM1 = ltsaCall.getCompositeName(sm)

    sm = ltsaCall.doCompile(M2)
    val αM2 = ltsaCall.getAllAlphabet(sm)
    nameM2 = ltsaCall.getCompositeName(sm)

    sm = ltsaCall.doCompile(P)
    val αP = ltsaCall.getAllAlphabet(sm)
    nameP = ltsaCall.getCompositeName(sm)

    println("========== M1, M2, P model information ==========")
    println("Machines: M1 = $nameM1, M2 = $nameM2, P = $nameP")
    Σ = (αM1 union αP) intersect αM2
    println("Σ of the language: $Σ")
  }

  fun run(): String {
    val ltsaCall = LTSACall()
    while (true) {
      println("========== Find assumption for M1 ==========")
      val A = lstar()
      val A_fsp = conjectureToFSP(A)
      println("========== Validate conjecture assumption with the environment M2 ==========")
      val counterExample = ltsaCall.propertyCheck(
        ltsaCall.doCompile("$M2\nproperty $A_fsp\n||Composite = ($nameM2 || C).", "Composite")
      )
      if (counterExample == null) {
        println("========== Find the weakest assumption for M1 ==========\n$A_fsp")
        return A_fsp
      } else {
        println("========== Counterexample found with environment M2 ==========\n$counterExample")
        val projected = counterExample.filter { it in Σ }
        val A_c = "AC = (${projected.joinToString(" -> ")} -> STOP) + {${Σ.joinToString(", ")}}."
        val check = ltsaCall.propertyCheck(
          ltsaCall.doCompile("$A_c\n$M1\n$P\n||Composite = (AC || $nameM1 || $nameP).", "Composite")
        )
        if (check == null) {
          println("========== Weaken the assumption for M1 ==========")
          witnessOfCounterExample(A, projected)
        } else {
          throw Error("P is violated in M1 || M2.")
        }
      }
    }
  }

  fun lstar(): Set<Triple<String, String, String>> {
    while (true) {
      update_T_withQueries()
      while (true) {
        val sa = isClosed()
        if (sa.isEmpty())
          break
        S.addAll(sa)
        update_T_withQueries()
      }
      val C = buildConjecture()
      val counterExample = checkCorrectness(C)
      if (counterExample == null) {
        return C
      } else {
        println("Counterexample found: $counterExample")
        witnessOfCounterExample(C, counterExample)
      }
    }
  }

  private fun witnessOfCounterExample(C: Set<Triple<String, String, String>>, counterExample: List<String>) {
    val projected = counterExample.filter { it in Σ }
    val size = projected.size
    println("Projected counterexample: $projected")
    for (i in projected.indices) {
      val si_1 = getStateAfterTrace(C, projected.subList(0, i))
      val si = getStateAfterTrace(C, projected.subList(0, i + 1))
      val qi_1 = membershipQuery(concat(si_1, *projected.subList(i, size).toTypedArray()))
      val qi = membershipQuery(concat(si, *projected.subList(i + 1, size).toTypedArray()))
      if (qi_1 != qi) {
        S.add(concat(si_1, projected[i]))
        E.add(concat(*projected.subList(i + 1, size).toTypedArray()))
        println("By witness counter example, S = $S, E = $E")
        return
      }
    }
  }

  private fun getStateAfterTrace(C: Set<Triple<String, String, String>>, trace: List<String>): String {
    var s = ""
    for (a in trace) {
      s = C.find { it.first == s && it.second == a }!!.third
    }
    return s
  }

  private fun checkCorrectness(C: Set<Triple<String, String, String>>): List<String>? {
    val ltsaCall = LTSACall()
    val fsp = conjectureToFSP(C)
    return ltsaCall.propertyCheck(
      ltsaCall.doCompile("$fsp\n$M1\n$P\n||Composite = (C || $nameM1 || $nameP).", "Composite")
    )
  }

  private fun buildConjecture(): Set<Triple<String, String, String>> {
    // Omit the error states
    val F = S.filter { T[it] == true }
    val δ = mutableSetOf<Triple<String, String, String>>()
    // Generate transitions of the conjecture automaton
    // The transition relation δ is defined as δ(s, a) = s' where \forall e \in E: T(sae) = T(s'e).
    for (s in F) {
      for (a in Σ) {
        val s_ = S.find { s_ -> E.forall { e -> T[concat(s, a, e)] == T[concat(s_, e)] } }
        if (s_ in F) {
          δ.add(Triple(s, a, s_!!))
        }
      }
    }
    println("Desire state machine: $δ")
    return δ
  }

  private fun conjectureToFSP(δ: Set<Triple<String, String, String>>): String {
    // Final states of the conjecture automaton
    val F = δ.map { it.first }.toSet()
    // Since F \subseteq S where S \subseteq Σ*, thus map F to other names to generate the FSP spec.
    val F_map = F.foldIndexed(mutableMapOf<String, String>()) { i, m, s ->
      m[s] = if (s == "") "C" else "C$i"
      m
    }
    // Divide the FSP spec into several sub processes, like A = (a -> B), B = (b -> A).
    val sm = F_map.values.fold(mutableMapOf<String, MutableList<String>>()) { m, s ->
      m[s] = mutableListOf()
      m
    }
    for (t in δ) {
      sm[F_map[t.first]]!!.add("${t.second} -> ${F_map[t.third]}")
    }
    // Build the FSP spec, C is the main process which must exist.
    val C = StringBuilder("C = (")
    C.append(sm["C"]!!.joinToString(" | "))
    C.append(')')
    // Other sub-process
    val C_tmp = sm.filter { it.key != "C" }
    if (C_tmp.isNotEmpty()) {
      C.append(",\n")
      val subs = C_tmp.map { "${it.key} = (${it.value.joinToString(" | ")})" }
      C.append(subs.joinToString(",\n"))
    }
    // Add the alphabet
    C.append(" + {${Σ.joinToString(", ")}}")
    C.append('.')
    println("Constructed state machine:\n$C")
    return C.toString()
  }

  private fun isClosed(): Set<String> {
    val sa = mutableSetOf<String>()
    // (S, E, T) is closed when \forall s \in S, \forall a \in Σ, \exists s' \in S, \forall e \in E: T(sae) = T(s'e)
    S.forall { s ->
      Σ.forall { a ->
        val re = S.exists { s_ -> E.forall { e -> T[concat(s, a, e)] == T[concat(s_, e)] } }
        // if (S, E, T) is not closed, add sa to S.
        if (!re) {
          sa.add(concat(s, a))
        }
        re
      }
    }
    if (sa.isEmpty()) {
      println("(S, E, T) is closed.")
    } else {
      println("(S, E, T) is not closed, add $sa to S.")
    }
    return sa
  }

  private fun update_T_withQueries() {
    // Update T by making membership queries on (S \cup S . Σ) . E
    val queries = (S union S.flatMap { s -> Σ.map { a -> concat(s, a) } })
      .flatMap { s -> E.map { e -> concat(s, e) } }
    for (query in queries) {
      T[query] = membershipQuery(query)
    }
    println("========== Updated T ==========")
    println(T)
  }

  /**
   * @param σ: the membership query to answer.
   */
  private fun membershipQuery(σ: String): Boolean {
    if (σ in T) {
      return T[σ]!!
    }
    val splited = σ.split(",")
    for (i in splited.indices) {
      val subQuery = splited.subList(0, i + 1).joinToString(",")
      if (subQuery in T && T[subQuery] == false) {
        return false
      }
    }

    val ltsaCall = LTSACall()
    val fsp = "A = (${σ.replace(",", " -> ")} -> STOP) + {${Σ.joinToString(", ")}}."
    return ltsaCall.propertyCheck(
      ltsaCall.doCompile("$fsp\n$M1\n$P\n||Composite = (A || $nameM1 || $nameP).", "Composite")
    ) == null
  }

  private fun concat(vararg words: String): String {
    return words.filter { it != "" }.joinToString(",")
  }

  private fun <T> Iterable<T>.forall(predicate: (T) -> Boolean): Boolean {
    for (x in this) {
      if (!predicate(x)) {
        return false
      }
    }
    return true
  }

  private fun <T> Iterable<T>.exists(predicate: (T) -> Boolean): Boolean {
    for (x in this) {
      if (predicate(x)) {
        return true
      }
    }
    return false
  }
}